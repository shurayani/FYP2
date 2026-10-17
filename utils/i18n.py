"""English / Bahasa Malaysia interface toggle (scope item vi).

t("English text") returns the Bahasa Malaysia translation when the sidebar language is 'ms';
any string that is not in the dictionary falls back to the English text."""
import streamlit as st

MS = {
    # ---- navigation / titles
    "Dashboard": "Papan Pemuka", "Account": "Akaun", "Login / Register": "Log Masuk / Daftar",
    "Receipts": "Resit", "Transactions": "Transaksi", "Categories": "Kategori", "Budget Goals": "Matlamat Belanjawan",
    "Reports": "Laporan", "Anomaly Alerts": "Amaran Anomali", "Forecast": "Ramalan", "Sync Status": "Status Penyegerakan",
    "Admin Panel": "Panel Admin", "Intelligent Personal Expense Categorization System": "Sistem Pengkategorian Perbelanjaan Peribadi Pintar",
    "Receipt & Transaction Entry": "Kemasukan Resit & Transaksi", "Transaction Management": "Pengurusan Transaksi",
    "Expense Category Management": "Pengurusan Kategori Perbelanjaan", "Budget Goal Management": "Pengurusan Matlamat Belanjawan",
    "Spending Report Management": "Pengurusan Laporan Perbelanjaan", "Anomaly Alert Management": "Pengurusan Amaran Anomali",
    "Spending Forecast Management": "Pengurusan Ramalan Perbelanjaan",
    # ---- common
    "Please log in to continue.": "Sila log masuk untuk meneruskan.", "Go to login": "Pergi ke log masuk",
    "Access denied. This page is only available to the administrator.": "Akses dinafikan. Halaman ini hanya untuk pentadbir.",
    "Online": "Dalam talian", "Offline": "Luar talian", "Log out": "Log keluar", "Log in": "Log masuk", "Login": "Log masuk",
    "Register": "Daftar", "Username": "Nama pengguna", "Password": "Kata laluan", "Email": "E-mel",
    "Confirm password": "Sahkan kata laluan", "Create account": "Cipta akaun", "Date": "Tarikh", "Merchant": "Pedagang",
    "Category": "Kategori", "Amount (RM)": "Jumlah (RM)", "Total": "Jumlah", "Month": "Bulan", "All": "Semua", "Name": "Nama",
    "Cancel": "Batal", "Delete": "Padam", "Rename": "Namakan semula", "Update": "Kemas kini", "Remove": "Buang", "Add": "Tambah",
    "Status": "Status", "Type": "Jenis", "System": "Sistem", "Custom": "Tersuai", "Active": "Aktif", "Deactivated": "Dinyahaktifkan",
    "Manual": "Manual", "Source": "Sumber", "Anomaly": "Anomali", "Filter": "Tapis", "Filters": "Penapis", "History": "Sejarah",
    "Settings": "Tetapan", "Profile": "Profil", "Record": "Rekod", "Table": "Jadual", "User": "Pengguna", "Never": "Tidak pernah",
    "Share": "Kongsi", "Spent": "Dibelanjakan", "Budget": "Belanjawan", "Remaining": "Baki", "Range": "Julat",
    "Role": "Peranan", "Member since": "Ahli sejak", "Uploaded": "Dimuat naik", "Linked transaction": "Transaksi berkaitan",
    "transaction(s)": "transaksi", "generated": "dijana", "Hello, {name}!": "Helo, {name}!",
    "Sync: {p} pending · {c} conflict(s)": "Segerak: {p} belum selesai · {c} konflik",
    # ---- auth messages
    "Username must be at least 3 characters.": "Nama pengguna mesti sekurang-kurangnya 3 aksara.",
    "Please enter a valid email address.": "Sila masukkan alamat e-mel yang sah.",
    "Password must be at least 6 characters.": "Kata laluan mesti sekurang-kurangnya 6 aksara.",
    "Passwords do not match.": "Kata laluan tidak sepadan.", "That username is already taken.": "Nama pengguna itu telah digunakan.",
    "That email is already registered.": "E-mel itu telah didaftarkan.",
    "Account created. You can now log in.": "Akaun dicipta. Anda boleh log masuk sekarang.",
    "Invalid username or password.": "Nama pengguna atau kata laluan tidak sah.",
    "This account has been deactivated.": "Akaun ini telah dinyahaktifkan.", "Profile updated.": "Profil dikemas kini.",
    "Current password is incorrect.": "Kata laluan semasa tidak betul.", "Password changed.": "Kata laluan ditukar.",
    # ---- account
    "Save profile": "Simpan profil", "Change password": "Tukar kata laluan", "Current password": "Kata laluan semasa",
    "New password": "Kata laluan baharu", "Confirm new password": "Sahkan kata laluan baharu",
    "The administrator password is configured through the ADMIN_PASSWORD setting, but you can also change it here.":
        "Kata laluan pentadbir ditetapkan melalui ADMIN_PASSWORD, tetapi anda juga boleh menukarnya di sini.",
    "Application preferences": "Keutamaan aplikasi", "The interface language can be changed from the sidebar (English / Bahasa Malaysia).":
        "Bahasa antara muka boleh ditukar dari bar sisi (English / Bahasa Malaysia).",
    "Data management": "Pengurusan data", "You have {tx} transaction(s) and {rc} receipt(s) stored.":
        "Anda mempunyai {tx} transaksi dan {rc} resit disimpan.",
    "Export your transactions from the Transactions page.": "Eksport transaksi anda dari halaman Transaksi.",
    "System information": "Maklumat sistem", "Deactivate account": "Nyahaktifkan akaun",
    "Deactivating your account will prevent you from logging in. Contact the administrator to reactivate it.":
        "Menyahaktifkan akaun akan menghalang anda log masuk. Hubungi pentadbir untuk mengaktifkannya semula.",
    "I understand and want to deactivate my account": "Saya faham dan mahu menyahaktifkan akaun saya",
    "Deactivate my account": "Nyahaktifkan akaun saya",
    # ---- dashboard
    "You are logged in as the administrator. Use the Admin Panel to manage users and system data.":
        "Anda log masuk sebagai pentadbir. Gunakan Panel Admin untuk mengurus pengguna dan data sistem.",
    "Total users": "Jumlah pengguna", "Total transactions": "Jumlah transaksi", "Receipts uploaded": "Resit dimuat naik",
    "Active anomaly alerts": "Amaran anomali aktif", "Open Admin Panel": "Buka Panel Admin",
    "Spent this month": "Dibelanjakan bulan ini", "Transactions recorded": "Transaksi direkodkan",
    "Most frequent category": "Kategori paling kerap", "Budget used": "Belanjawan digunakan",
    "Unresolved alerts": "Amaran belum selesai", "Forecast next month": "Ramalan bulan depan",
    "No transactions yet. Upload a receipt or add a transaction manually to get started.":
        "Belum ada transaksi. Muat naik resit atau tambah transaksi secara manual untuk bermula.",
    "Add your first transaction": "Tambah transaksi pertama anda", "Monthly spending trend": "Trend perbelanjaan bulanan",
    "Category breakdown": "Pecahan kategori", "No spending recorded this month.": "Tiada perbelanjaan direkodkan bulan ini.",
    "Budget progress": "Kemajuan belanjawan", "No budget goals set for this month.": "Tiada matlamat belanjawan ditetapkan bulan ini.",
    "Set a budget goal": "Tetapkan matlamat belanjawan", "Anomaly alerts": "Amaran anomali",
    "No active anomaly alerts.": "Tiada amaran anomali aktif.", "View all alerts": "Lihat semua amaran",
    "Forecast preview": "Pratonton ramalan", "No forecast yet. Open the Forecast page and press Recalculate.":
        "Belum ada ramalan. Buka halaman Ramalan dan tekan Kira semula.", "Open forecasts": "Buka ramalan",
    "Recent transactions": "Transaksi terkini", "Financial insights": "Pandangan kewangan", "Quick navigation": "Navigasi pantas",
    # ---- receipts
    "OCR Receipt Upload": "Muat Naik Resit OCR", "Manual Data Form": "Borang Data Manual", "Receipt Gallery": "Galeri Resit",
    "Gemini AI is used when online; PaddleOCR is used automatically when offline or if Gemini fails.":
        "Gemini AI digunakan apabila dalam talian; PaddleOCR digunakan secara automatik apabila luar talian atau Gemini gagal.",
    "Image source": "Sumber imej", "Upload file": "Muat naik fail", "Take a photo": "Ambil gambar",
    "Receipt image (JPEG or PNG, up to 10 MB)": "Imej resit (JPEG atau PNG, sehingga 10 MB)",
    "Take a photo of the receipt": "Ambil gambar resit", "Only JPEG or PNG images are accepted.": "Hanya imej JPEG atau PNG diterima.",
    "Image is larger than 10 MB.": "Imej melebihi 10 MB.", "Extract transaction details": "Ekstrak butiran transaksi",
    "Reading receipt...": "Membaca resit...", "Extraction failed": "Pengekstrakan gagal", "Extracted with": "Diekstrak dengan",
    "Some fields could not be read reliably. Please complete them below.": "Sesetengah medan tidak dapat dibaca dengan pasti. Sila lengkapkan di bawah.",
    "Please check and correct the values before saving.": "Sila semak dan betulkan nilai sebelum menyimpan.",
    "Total amount (RM)": "Jumlah keseluruhan (RM)", "Confirm and save": "Sahkan dan simpan", "Discard": "Buang",
    "Merchant and a positive amount are required.": "Pedagang dan jumlah positif diperlukan.", "Transaction saved.": "Transaksi disimpan.",
    "Record a transaction without a receipt. Leave the category on Auto to let the classifier decide.":
        "Rekod transaksi tanpa resit. Biarkan kategori pada Auto supaya pengelas memutuskan.",
    "Auto (classify automatically)": "Auto (kelaskan secara automatik)", "Save transaction": "Simpan transaksi",
    "No receipts uploaded yet.": "Belum ada resit dimuat naik.", "Image file not found on this device.": "Fail imej tidak ditemui pada peranti ini.",
    "Replace / delete": "Ganti / padam", "New image": "Imej baharu", "Replace image": "Ganti imej", "Delete receipt": "Padam resit",
    # ---- transactions
    "Date range": "Julat tarikh", "Maximum amount (RM)": "Jumlah maksimum (RM)", "0 = no limit": "0 = tiada had",
    "Entry method": "Kaedah kemasukan", "No transactions match the current filters.": "Tiada transaksi sepadan dengan penapis semasa.",
    "Export CSV": "Eksport CSV", "Add transaction manually": "Tambah transaksi secara manual",
    "Correct or delete a transaction": "Betulkan atau padam transaksi", "Select a transaction": "Pilih transaksi",
    "Save changes": "Simpan perubahan", "Delete transaction": "Padam transaksi", "Transaction updated.": "Transaksi dikemas kini.",
    "Transaction deleted.": "Transaksi dipadam.",
    # ---- categories
    "System categories (read-only)": "Kategori sistem (baca sahaja)", "Total spent": "Jumlah dibelanjakan",
    "Your custom categories": "Kategori tersuai anda", "New category name": "Nama kategori baharu", "Create category": "Cipta kategori",
    "Please enter a category name.": "Sila masukkan nama kategori.", "A category with that name already exists.": "Kategori dengan nama itu sudah wujud.",
    "Category created.": "Kategori dicipta.", "You have no custom categories yet.": "Anda belum mempunyai kategori tersuai.",
    "{n} transaction(s) use this category. Choose a fallback category to reassign them to.":
        "{n} transaksi menggunakan kategori ini. Pilih kategori ganti untuk memindahkannya.",
    "Reassign to": "Pindahkan ke", "Confirm delete": "Sahkan padam",
    # ---- budget
    "Current Month": "Bulan Semasa", "Monthly budget (RM)": "Belanjawan bulanan (RM)", "Save goal": "Simpan matlamat",
    "Budget must be greater than zero.": "Belanjawan mesti lebih daripada sifar.", "Budget goal saved.": "Matlamat belanjawan disimpan.",
    "No budget goals for this month yet.": "Belum ada matlamat belanjawan bulan ini.", "Overall budget": "Belanjawan keseluruhan",
    "Adjust amount": "Laraskan jumlah", "No budget history in the last 6 months.": "Tiada sejarah belanjawan dalam 6 bulan lepas.",
    # ---- reports
    "Generate report": "Jana laporan", "Regenerate report": "Jana semula laporan", "Report saved.": "Laporan disimpan.",
    "Saved reports": "Laporan tersimpan", "No reports saved yet. Choose a month and press Generate report.":
        "Belum ada laporan tersimpan. Pilih bulan dan tekan Jana laporan.", "Highest category": "Kategori tertinggi",
    "Top merchant": "Pedagang teratas", "Average per day": "Purata sehari", "Share": "Bahagian", "Variance": "Varians",
    "Month-on-month trend": "Trend bulan ke bulan", "Top merchants": "Pedagang teratas", "Regenerate": "Jana semula",
    "Delete report": "Padam laporan", "Transactions are checked per category. A transaction is flagged when |Z| > {z} (needs at least {n} transactions in the category).":
        "Transaksi disemak mengikut kategori. Transaksi ditandakan apabila |Z| > {z} (memerlukan sekurang-kurangnya {n} transaksi dalam kategori).",
    # ---- anomaly
    "Re-scan transactions": "Imbas semula transaksi", "Clear all resolved": "Kosongkan semua yang selesai",
    "Scan complete: {f} anomalous transaction(s), {n} new alert(s).": "Imbasan selesai: {f} transaksi anomali, {n} amaran baharu.",
    "Active alerts": "Amaran aktif", "above": "melebihi", "below": "di bawah", "standard deviations": "sisihan piawai",
    "the category mean": "purata kategori", "High": "Tinggi", "Medium": "Sederhana", "Reviewed": "Disemak", "Dismiss": "Ketepikan",
    "Resolved alerts": "Amaran diselesaikan", "reviewed": "disemak", "dismissed": "diketepikan", "active": "aktif",
    # ---- forecast
    "Next-month forecasts per category are computed offline with Prophet from your monthly history (at least {n} months per category).":
        "Ramalan bulan depan bagi setiap kategori dikira secara luar talian dengan Prophet daripada sejarah bulanan anda (sekurang-kurangnya {n} bulan setiap kategori).",
    "Recalculate forecasts": "Kira semula ramalan", "Forecasting...": "Meramal...", "Forecast failed": "Ramalan gagal",
    "{n} forecast(s) saved for {m}.": "{n} ramalan disimpan untuk {m}.",
    "Not enough history to forecast yet. Record transactions across at least {n} different months.":
        "Sejarah belum mencukupi untuk meramal. Rekod transaksi merentasi sekurang-kurangnya {n} bulan berbeza.",
    "Skipped (not enough history): ": "Dilangkau (sejarah tidak mencukupi): ",
    "No forecasts saved yet. Press Recalculate forecasts.": "Belum ada ramalan tersimpan. Tekan Kira semula ramalan.",
    "Forecast month": "Bulan ramalan", "Total forecast": "Jumlah ramalan", "vs this month": "berbanding bulan ini",
    "higher": "lebih tinggi", "lower": "lebih rendah", "similar": "hampir sama", "AI spending insights": "Pandangan perbelanjaan AI",
    "Optional: add GEMINI_API_KEY to .env to get written insights when online.": "Pilihan: tambah GEMINI_API_KEY dalam .env untuk mendapat pandangan bertulis apabila dalam talian.",
    "Offline — showing the Prophet forecast only. AI insights appear when you are online.":
        "Luar talian — hanya ramalan Prophet dipaparkan. Pandangan AI muncul apabila anda dalam talian.",
    "Generate AI insights": "Jana pandangan AI", "Asking Gemini...": "Bertanya Gemini...", "AI insights are unavailable right now.": "Pandangan AI tidak tersedia sekarang.",
    # ---- sync
    "Connection": "Sambungan", "Last sync": "Segerak terakhir", "Pending changes": "Perubahan belum selesai", "Conflicts": "Konflik",
    "Supabase is not configured. IPECS works fully offline; add SUPABASE_URL and SUPABASE_KEY to .env to enable synchronisation.":
        "Supabase belum dikonfigurasi. IPECS berfungsi sepenuhnya luar talian; tambah SUPABASE_URL dan SUPABASE_KEY dalam .env untuk mengaktifkan penyegerakan.",
    "Sync Now": "Segerak Sekarang", "Synchronising...": "Menyegerak...", "Conflicts and the version kept": "Konflik dan versi yang dikekalkan",
    "No conflicts.": "Tiada konflik.", "Kept version": "Versi dikekalkan", "Local time": "Masa tempatan", "Remote time": "Masa jauh",
    "local": "tempatan", "remote": "jauh", "Record sync status": "Status penyegerakan rekod", "No records tracked yet.": "Belum ada rekod dijejak.",
    "Operation": "Operasi", "Local change": "Perubahan tempatan", "Synced at": "Disegerakkan pada",
    "Conflict on {tbl} record {rid}: the {kept} version was kept (last-write-wins).": "Konflik pada rekod {tbl} {rid}: versi {kept} dikekalkan (penulisan terakhir menang).",
    "Sync runs automatically once when you log in (if configured and online) and whenever you press Sync Now.":
        "Penyegerakan berjalan automatik sekali apabila anda log masuk (jika dikonfigurasi dan dalam talian) dan setiap kali anda menekan Segerak Sekarang.",
    # ---- admin
    "User Management": "Pengurusan Pengguna", "System Overview": "Gambaran Sistem", "Category Management": "Pengurusan Kategori",
    "Transaction Oversight": "Pemantauan Transaksi", "Registered users": "Pengguna berdaftar", "Search users": "Cari pengguna",
    "Registered": "Didaftarkan", "Select a user": "Pilih pengguna", "Reactivate account": "Aktifkan semula akaun", "No users found.": "Tiada pengguna ditemui.",
    "No transactions yet.": "Belum ada transaksi.", "Transactions by category": "Transaksi mengikut kategori", "Daily activity": "Aktiviti harian",
    "System integrity": "Integriti sistem", "Database": "Pangkalan data", "OCR service (PaddleOCR)": "Perkhidmatan OCR (PaddleOCR)",
    "installed": "dipasang", "not installed": "tidak dipasang", "AI module (Gemini)": "Modul AI (Gemini)", "API key configured": "Kunci API dikonfigurasi",
    "no API key": "tiada kunci API", "New system category name": "Nama kategori sistem baharu", "Create system category": "Cipta kategori sistem",
    "The seven predefined categories are protected. Other categories can be renamed or deleted.":
        "Tujuh kategori pratakrif dilindungi. Kategori lain boleh dinamakan semula atau dipadam.",
    "Select a category": "Pilih kategori", "Rename to": "Namakan semula kepada", "Flag a suspicious transaction": "Tandakan transaksi mencurigakan",
    "Flag for review": "Tandakan untuk semakan", "This transaction already has an alert.": "Transaksi ini sudah mempunyai amaran.",
    "Alert created for the user.": "Amaran dicipta untuk pengguna.",
    # ---- the seven predefined categories
    "Food and Beverage": "Makanan dan Minuman", "Groceries": "Barangan Runcit", "Transport": "Pengangkutan", "Utilities": "Utiliti",
    "Education": "Pendidikan", "Health": "Kesihatan", "Entertainment": "Hiburan",
}


def lang() -> str:
    try:
        return st.session_state.get("lang", "en")
    except Exception:
        return "en"


def t(text: str, **kw) -> str:
    out = MS.get(text, text) if lang() == "ms" else text
    return out.format(**kw) if kw else out
