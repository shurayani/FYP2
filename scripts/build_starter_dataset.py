"""Builds a STARTER labelled dataset (training/receipt_dataset.csv) of Malaysian merchant names.
Replace/extend it with your own labelled receipts (columns: merchant,category) before the final
evaluation, then re-run:  python training/train_model.py"""
import csv
import random
from pathlib import Path

random.seed(42)

MERCHANTS = {
 "Food and Beverage": ["KFC", "McDonald's", "Burger King", "Pizza Hut", "Domino's Pizza", "Subway", "Starbucks",
   "Old Town White Coffee", "Secret Recipe", "Dunkin Donuts", "Texas Chicken", "Marrybrown", "Nando's", "Sushi King",
   "Kenny Rogers Roasters", "Chatime", "Tealive", "Gong Cha", "The Coffee Bean", "ZUS Coffee", "Kopitiam", "Restoran Nasi Kandar",
   "Nasi Lemak Ayam Berempah", "Warung Makan Pak Ali", "Mamak Corner Restaurant", "Roti Canai Station", "Kedai Kopi Ah Seng",
   "Pak Mat Satay", "Ikan Bakar Corner", "Restoran Tomyam", "Cafe Latte House", "Bakery Cafe", "Kafe Siswa", "Dewan Makan",
   "Medan Selera", "Food Court", "Ayam Penyet Ria", "Bubble Tea Station", "Sweet Dessert Cafe", "Restoran Pelita"],
 "Groceries": ["Tesco", "Lotus's", "Mydin", "Giant Hypermarket", "AEON Big", "Jaya Grocer", "Village Grocer", "99 Speedmart",
   "KK Mart", "7-Eleven", "FamilyMart", "MyNews", "Econsave", "NSK Trade City", "Pasar Borong", "Pasar Tani",
   "Kedai Runcit Pak Din", "Mini Market Sri Murni", "Cold Storage", "Ben's Independent Grocer", "Sapura Mart", "Hero Market",
   "Segi Fresh", "Gaya Mart", "Mart Sabah", "Pasar Basah", "Fresh Mart Supermarket", "Kedai Sayur", "Maxim Grocery", "Whole Foods Store"],
 "Transport": ["Grab", "GrabCar", "Petronas", "Shell", "Petron", "Caltex", "BHPetrol", "Touch n Go", "TNG eWallet Reload",
   "Rapid KL", "KTM Komuter", "LRT Station", "MRT Kajang Line", "Bas Sabah", "Bas Persiaran UMS", "AirAsia", "Malaysia Airlines",
   "Firefly Airlines", "MYTeksi", "inDrive", "Maxim Ride", "Parking Kompleks", "PLUS Highway Toll", "Tol LDP", "Stesen Minyak Petronas",
   "Shell Select", "KLIA Ekspres", "ERL Transit", "Kereta Api Tanah Melayu", "Bus Terminal Kota Kinabalu", "Bayaran Tempat Letak Kereta"],
 "Utilities": ["TNB Tenaga Nasional", "Sabah Electricity SESB", "Air Selangor", "Jabatan Air Sabah", "Syabas Water", "Indah Water Konsortium",
   "TM Unifi", "Maxis", "Celcom", "Digi Telecommunications", "U Mobile", "Yes 4G", "Time Internet", "Astro", "Telekom Malaysia Streamyx",
   "Prepaid Reload Maxis", "Digi Prepaid Topup", "Celcom Xpax Reload", "Hotlink Prepaid", "Bil Elektrik", "Bil Air", "Bayaran Internet",
   "Syarikat Air Negeri Sembilan", "Gas Malaysia", "Pengurusan Sisa Pepejal", "Cukai Pintu", "Unifi Mobile", "redONE Mobile", "Tune Talk", "XOX Mobile"],
 "Education": ["Popular Bookstore", "MPH Bookstores", "Kinokuniya", "Times Bookstore", "Universiti Malaysia Sabah Bursar", "Yuran Pengajian UMS",
   "Kedai Buku UMS", "Photostat Centre", "Fotostat dan Cetak", "Print Shop Kampus", "Stationery Mart", "Kedai Alat Tulis", "Pusat Tuisyen",
   "Coursera", "Udemy", "Pearson Education", "Perpustakaan Tunku Abdul Rahman", "SPM Tuition Centre", "Bayaran Peperiksaan", "MUET Registration",
   "IELTS Registration", "Lab Fee Faculty", "Kolej Kediaman Yuran", "Buku Teks Store", "Art Friend", "Staples Office Supplies", "Daiso Stationery",
   "Study Material Supplies", "Kursus Bahasa Inggeris", "Language Centre Fee"],
 "Health": ["Guardian Pharmacy", "Watsons", "Caring Pharmacy", "Alpro Pharmacy", "Farmasi Kampus", "Farmasi Sri Ramai", "Klinik Kesihatan",
   "Klinik Dr Lim", "Klinik Mediviron", "Poliklinik Sabah", "Hospital Queen Elizabeth", "Hospital Likas", "KPJ Healthcare", "Gleneagles Hospital",
   "Pantai Hospital", "Columbia Asia", "Klinik Pergigian", "Dental Clinic", "Optik Mata Specs", "Focus Point", "Health Lane Family Pharmacy",
   "Vitamin Shop", "Sunway Medical Centre", "Klinik Pakar Kanak-kanak", "Physiotherapy Centre", "Pusat Kesihatan UMS", "Medicine Store",
   "Ubat Farmasi Wellness", "Pharmacy Care Plus", "BIG Pharmacy"],
 "Entertainment": ["Golden Screen Cinemas GSC", "TGV Cinemas", "MBO Cinemas", "Netflix", "Spotify", "Disney Plus Hotstar", "Viu Premium",
   "iflix", "Steam Games", "Google Play Games", "PlayStation Store", "Nintendo eShop", "Mobile Legends Diamond", "Karaoke Neway", "Redbox Karaoke",
   "Funtasy Arcade", "Timezone Arcade", "Sunway Lagoon", "Genting Highlands Theme Park", "Bowling Centre", "Escape Room", "Concert Ticket Ticket2u",
   "Ticketmaster", "Bioskop Cineplex", "YouTube Premium", "Apple Music", "Xbox Game Pass", "Cinema Tickets", "Wet World Waterpark", "Laser Tag Arena"],
}
SUFFIX = ["", "", "", " Sdn Bhd", " Kota Kinabalu", " Kuala Lumpur", " Sabah", " Cawangan", " Branch", " Mall", " Outlet", " Jalan Tun Fuad", " Damansara", " Penampang"]
PREFIX = ["", "", "", "", "Kedai ", "Restoran ", "Cafe "]

rows = []
for cat, names in MERCHANTS.items():
    for n in names:
        variants = {n}
        for _ in range(7):
            v = (random.choice(PREFIX) if cat in ("Food and Beverage", "Groceries") and not n.startswith(("Kedai", "Restoran", "Cafe")) else "") + n + random.choice(SUFFIX)
            if random.random() < 0.3:
                v = v.upper()
            variants.add(v.strip())
        for v in sorted(variants):
            rows.append((v, cat))
random.shuffle(rows)
out = Path(__file__).resolve().parent.parent / "training" / "receipt_dataset.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["merchant", "category"])
    w.writerows(rows)
print(f"wrote {len(rows)} rows to {out}")
