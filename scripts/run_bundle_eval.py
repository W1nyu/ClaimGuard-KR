"""청구 건 단위 기능 평가.

1. 위임장 칸 추출 정확도 (엔진 A, 검증 위임장 200장)
2. 위임 필요 자동 감지: 청구서의 예금주 ≠ 피보험자를 OCR 값으로 얼마나 맞게 잡는가 (정답 값 기준)
3. 서류 대조의 거짓 불일치: 데이터의 청구서·위임장은 서로 다른 사람이라 실제 쌍이 없다.
   그래서 '내용이 일치하는 쌍'을 만들어 한쪽만 OCR 값으로 바꿨을 때 불일치로 잘못 잡히는 비율을 잰다.
   - 청구서 쪽 오류: 청구서 OCR 값 vs 그 청구서 정답으로 만든 위임장
   - 위임장 쪽 오류: 위임장 OCR 값 vs 그 위임장 정답으로 만든 청구서

실행: .venv/Scripts/python -m scripts.run_bundle_eval
"""
import csv
import json

from src.bundle import cross_check, needs_delegation
from src.extract_paddle import extract_fields, load_recognizer
from src.load_data import CATEGORY_BY_FORM, PROJECT_ROOT, list_documents, load_image
from src.metrics import is_exact
from src.route import CONFIDENCE_THRESHOLD

GT_DIR = PROJECT_ROOT / "data" / "processed" / "ground_truth"
PRED_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
RESULTS = PROJECT_ROOT / "results"
CROSS_RULES = ["B02", "B03", "B04", "B05"]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def poa_from_claim(c):
    """청구서 정답 값으로 내용이 일치하는 위임장 값을 만든다."""
    return {"수임인_성명": c.get("예금주", ""), "수임인_은행명": c.get("은행명", ""), "수임인_계좌번호": c.get("계좌번호", ""),
            "위임사항_피보험자": c.get("피보험자_성명", ""),
            "사고_년": c.get("사고_년", ""), "사고_월": c.get("사고_월", ""), "사고_일": c.get("사고_일", "")}


def claim_from_poa(p):
    """위임장 정답 값으로 내용이 일치하는 청구서 값을 만든다."""
    return {"예금주": p.get("수임인_성명", ""), "은행명": p.get("수임인_은행명", ""), "계좌번호": p.get("수임인_계좌번호", ""),
            "피보험자_성명": p.get("위임사항_피보험자", ""),
            "사고_년": p.get("사고_년", ""), "사고_월": p.get("사고_월", ""), "사고_일": p.get("사고_일", "")}


def false_mismatch(pairs):
    """[(청구서 값, 위임장 값)] 중 규칙별로 '불일치'로 잡힌 비율. 쌍은 모두 실제로는 일치한다."""
    counts = {rule: 0 for rule in CROSS_RULES}
    compared = {rule: 0 for rule in CROSS_RULES}
    for claim_values, poa_values in pairs:
        for check in cross_check(claim_values, poa_values):
            if check["status"] == "unknown":
                continue
            compared[check["rule"]] += 1
            counts[check["rule"]] += check["status"] == "fail"
    return {rule: (counts[rule], compared[rule]) for rule in CROSS_RULES}


def main():
    rows = []

    # 1. 위임장 추출 (엔진 A)
    truth_poa = {r["doc_id"]: r["fields"] for r in read_jsonl(GT_DIR / "val_12.jsonl")}
    recognizer = load_recognizer()
    predicted_poa = {}
    exact = total = 0
    for doc in list_documents("val", [CATEGORY_BY_FORM["12"]]):
        extracted = extract_fields(load_image(doc), "12", recognizer)
        predicted_poa[doc["doc_id"]] = {k: v["value"] for k, v in extracted.items()}
        for name, field in extracted.items():
            total += 1
            exact += is_exact(field["value"], truth_poa[doc["doc_id"]].get(name, ""), name)
    rows.append({"항목": "위임장 칸 완전 일치율 (엔진 A)", "값": round(exact / total, 3), "대상": f"{len(predicted_poa)}장"})

    # 2. 위임 필요 자동 감지 (엔진 A, 청구서 신양식)
    truth_claim = {r["doc_id"]: r["fields"] for r in read_jsonl(GT_DIR / "val_16.jsonl")}
    predicted_claim = {r["doc_id"]: {k: v["value"] for k, v in r["fields"].items()}
                       for r in read_jsonl(PRED_DIR / "paddle_val_16.jsonl")}
    tp = fp = fn = tn = 0
    for doc_id, truth in truth_claim.items():
        actual, detected = needs_delegation(truth), needs_delegation(predicted_claim[doc_id])
        tp += actual and detected
        fp += (not actual) and detected
        fn += actual and not detected
        tn += (not actual) and not detected
    rows += [
        {"항목": "위임 필요 서류 비율 (정답)", "값": round((tp + fn) / len(truth_claim), 3), "대상": f"{len(truth_claim)}장"},
        {"항목": "위임 필요 감지 재현율 (놓치지 않은 비율)", "값": round(tp / (tp + fn), 3) if tp + fn else "", "대상": f"{tp + fn}건"},
        {"항목": "위임 필요 감지 정밀도 (맞게 잡은 비율)", "값": round(tp / (tp + fp), 3) if tp + fp else "", "대상": f"{tp + fp}건"},
    ]

    # 2-1. 설계 보정: 이름 확신도가 모두 높을 때만 위임 서류를 자동 추가 (낮으면 담당자 확인)
    scores = {r["doc_id"]: r["fields"] for r in read_jsonl(PRED_DIR / "paddle_val_16.jsonl")}
    auto_right = auto_wrong = deferred = 0
    for doc_id, truth in truth_claim.items():
        if not needs_delegation(predicted_claim[doc_id]):
            continue
        confident = min(scores[doc_id][f]["score"] for f in ["예금주", "피보험자_성명"]) >= CONFIDENCE_THRESHOLD
        if not confident:
            deferred += 1
        elif needs_delegation(truth):
            auto_right += 1
        else:
            auto_wrong += 1
    rows += [
        {"항목": "[보정 전] 위임 서류를 잘못 요구한 건 (예금주=피보험자인데)", "값": fp, "대상": f"{fp + tn}건 중"},
        {"항목": "[보정 후] 위임 서류를 잘못 요구한 건", "값": auto_wrong, "대상": f"{fp + tn}건 중"},
        {"항목": "[보정 후] 위임 서류 자동 추가 (맞게)", "값": auto_right, "대상": f"{tp}건 중"},
        {"항목": "[보정 후] 이름 확신도 낮아 담당자 확인으로 넘긴 건", "값": deferred, "대상": f"{tp + fp}건 중"},
    ]

    # 3. 일치하는 쌍에서 거짓 불일치
    claim_side = false_mismatch([(predicted_claim[d], poa_from_claim(truth_claim[d])) for d in truth_claim])
    poa_side = false_mismatch([(claim_from_poa(truth_poa[d]), predicted_poa[d]) for d in truth_poa])
    labels = {"B02": "수임인·예금주", "B03": "수령 계좌", "B04": "피보험자", "B05": "사고일"}
    for rule in CROSS_RULES:
        for side, result in [("청구서 OCR", claim_side), ("위임장 OCR", poa_side)]:
            wrong, compared = result[rule]
            rows.append({"항목": f"거짓 불일치 {rule} {labels[rule]} — {side}",
                         "값": round(wrong / compared, 3) if compared else "", "대상": f"{compared}쌍"})

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "eval_bundle.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["항목", "값", "대상"])
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
