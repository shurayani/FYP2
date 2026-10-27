"""One-time patch #4: 'low confidence' warning when the classifier is not sure about the category.
Run once from the project folder:   python patch_v4.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- utils/config.py
p = ROOT / "utils" / "config.py"
s = p.read_text(encoding="utf-8")
if "LOW_CONFIDENCE_THRESHOLD" not in s:
    s += ("LOW_CONFIDENCE_THRESHOLD = 0.40     # below this the user is asked to double-check the category\n"
          "                                    # (re-tune after retraining: Naive Bayes probabilities depend on the dataset)\n")
    p.write_text(s, encoding="utf-8")
    print("config.py patched")

# ---- utils/i18n.py
p = ROOT / "utils" / "i18n.py"
s = p.read_text(encoding="utf-8")
if "Low confidence" not in s:
    s += '''

MS.update({
    "Low confidence: the suggested category may be wrong (it is based on the merchant name only). Please check it.":
        "Keyakinan rendah: kategori yang dicadangkan mungkin salah (ia berdasarkan nama kedai sahaja). Sila semak.",
    "Low confidence: please check the category in the Transactions page.":
        "Keyakinan rendah: sila semak kategori di halaman Transaksi.",
})
'''
    p.write_text(s, encoding="utf-8")
    print("i18n.py patched")

# ---- pages/2_Receipts.py
p = ROOT / "pages" / "2_Receipts.py"
s = p.read_text(encoding="utf-8")
if "LOW_CONFIDENCE_THRESHOLD" in s:
    print("2_Receipts.py already patched")
else:
    def swap(old, new):
        global s
        assert old in s, "not found: " + old[:60]
        s = s.replace(old, new, 1)

    swap("from utils.i18n import t",
         "from utils.config import LOW_CONFIDENCE_THRESHOLD\nfrom utils.i18n import t")
    swap('                        res["category_id"] = classifier.predict_category_id(res["merchant"])\n',
         '                        cat_name, conf = classifier.predict_with_confidence(res["merchant"])\n'
         '                        res["category_id"] = db.category_uuid(cat_name)\n'
         '                        res["confidence"] = conf\n')
    swap('        st.caption(t("Please check and correct the values before saving."))\n',
         '        if res.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD:\n'
         '            st.warning(t("Low confidence: the suggested category may be wrong (it is based on the merchant name only). Please check it."))\n'
         '        st.caption(t("Please check and correct the values before saving."))\n')
    swap('            cid = classifier.predict_category_id(merchant) if cat_choice == auto else cats[cat_choice]\n',
         '            low_conf = False\n'
         '            if cat_choice == auto:\n'
         '                cat_name, conf = classifier.predict_with_confidence(merchant)\n'
         '                cid, low_conf = db.category_uuid(cat_name), conf < LOW_CONFIDENCE_THRESHOLD\n'
         '            else:\n'
         '                cid = cats[cat_choice]\n')
    swap('''            st.success(f"{t('Transaction saved.')} {t('Category')}: {id_to_label[cid]}")\n''',
         '''            st.success(f"{t('Transaction saved.')} {t('Category')}: {id_to_label[cid]}")\n'''
         '            if low_conf:\n'
         '                st.warning(t("Low confidence: please check the category in the Transactions page."))\n')
    p.write_text(s, encoding="utf-8")
    print("2_Receipts.py patched")
print("Done. Restart Streamlit.")