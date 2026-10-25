import sqlite3
import os
import secrets
import hashlib
import hmac
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "eventora.db")

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, key_hex = stored_hash.split("$")
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(computed.hex(), key_hex)
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reseed=False):
    if force_reseed and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT 'General',
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        venue TEXT NOT NULL,
        capacity INTEGER NOT NULL DEFAULT 100,
        budget REAL DEFAULT 0,
        expenses REAL DEFAULT 0,
        ticket_price REAL DEFAULT 199,
        banner_url TEXT DEFAULT '',
        schedule_json TEXT DEFAULT '[]',
        rating REAL DEFAULT 4.9,
        review_count INTEGER DEFAULT 1,
        status TEXT DEFAULT 'published',
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS guests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        rsvp TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        assignee TEXT DEFAULT '',
        due_date TEXT,
        status TEXT DEFAULT 'todo',
        priority TEXT DEFAULT 'medium',
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        attendee_name TEXT NOT NULL,
        attendee_email TEXT NOT NULL,
        ticket_id TEXT UNIQUE NOT NULL,
        ticket_tier TEXT DEFAULT 'Standard Pass (₹199)',
        quantity INTEGER DEFAULT 1,
        total_amount REAL DEFAULT 199,
        checked_in_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        author_name TEXT NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        event_id INTEGER,
        message TEXT NOT NULL,
        read_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE NOT NULL,
        event_id INTEGER NOT NULL,
        attendee_name TEXT NOT NULL,
        attendee_email TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'INR',
        method TEXT DEFAULT 'upi',
        status TEXT DEFAULT 'pending',
        transaction_id TEXT,
        payment_details_json TEXT DEFAULT '{}',
        ticket_id TEXT,
        created_at TEXT NOT NULL,
        paid_at TEXT,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    );
    """)

    # Safe migrations for existing registrations table
    for col_name, col_type in [
        ("payment_status", "TEXT DEFAULT 'paid'"),
        ("payment_method", "TEXT DEFAULT 'upi'"),
        ("transaction_id", "TEXT"),
        ("order_id", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE registrations ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    conn.commit()

    # Seed default dataset if database is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    if count == 0:
        print("[Evntra-Python] Seeding enhanced demo dataset with ₹199 pricing and new events...")
        now = datetime.now()
        pw_hash = hash_password("Password123!@#")

        # Demo User
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, ("Aarav Sharma", "organizer@eventora.io", pw_hash, now.isoformat()))
        demo_user_id = cursor.lastrowid

        # Rich Event Schedules
        sched_comedy = json.dumps([
            {"time": "07:30 PM", "title": "Doors Open & Welcome Drinks", "desc": "Grab your mocktails and get seated"},
            {"time": "08:00 PM", "title": "Opening Act: Rising Comics Showcase", "desc": "Featuring 3 up-and-coming standup talents"},
            {"time": "08:45 PM", "title": "Headline Set with Special Guests", "desc": "Unfiltered 45-minute comedy special"},
            {"time": "09:30 PM", "title": "Open Mic & Crowd Interaction", "desc": "Improv session and photo opportunities"}
        ])

        sched_music = json.dumps([
            {"time": "06:00 PM", "title": "Acoustic Warm-Up & Coffee Tasting", "desc": "Handcrafted pour-overs and acoustic guitar chords"},
            {"time": "07:00 PM", "title": "Indie Folk & Songwriter Showcase", "desc": "Live acoustic performances by regional indie artists"},
            {"time": "08:30 PM", "title": "Open Jam Session & Harmonies", "desc": "Audience participation and collaborative acoustic jams"}
        ])

        sched_stars = json.dumps([
            {"time": "09:00 PM", "title": "Rooftop Welcome & Telescope Calibration", "desc": "Briefing on planetary alignments and celestial maps"},
            {"time": "09:45 PM", "title": "Deep-Sky Nebula & Saturn Observation", "desc": "Guided stargazing session through high-powered optical lenses"},
            {"time": "11:00 PM", "title": "Astrophotography & Hot Cocoa Lounge", "desc": "Learn how to photograph constellations on your smartphone"}
        ])

        sched_pottery = json.dumps([
            {"time": "11:00 AM", "title": "Clay Preparation & Centering Masterclass", "desc": "Hands-on fundamentals of working with the potter wheel"},
            {"time": "12:15 PM", "title": "Throwing & Shaping Ceramic Vases", "desc": "Create your own customized pottery piece with guidance"},
            {"time": "01:15 PM", "title": "Glazing Techniques & Kiln Firing Demo", "desc": "Pick your favorite glazes and color finishes"}
        ])

        sched_summit = json.dumps([
            {"time": "09:30 AM", "title": "Keynote: Frontier Autonomous LLMs", "desc": "Opening address by leading research directors"},
            {"time": "11:00 AM", "title": "Panel: The Future of Spatial & Neural UI", "desc": "Product leaders debate the death of traditional screens"},
            {"time": "02:00 PM", "title": "Live Demos & VC Pitch Competition", "desc": "10 AI startups pitch live for ₹2.5Cr funding"}
        ])

        # 8 High-Impact Events with ₹199 per person focus
        events_data = [
            (
                demo_user_id,
                "Friday Night Standup Comedy Lounge",
                "An evening of side-splitting laughter featuring top national standup comedians, hilarious crowd-work, and chilled artisan drinks in an intimate lounge setting.",
                "Comedy",
                (now + timedelta(days=4)).strftime("%Y-%m-%d"),
                "19:30",
                "The Laugh Cellar, Indiranagar, Bengaluru",
                120,
                35000,
                18500,
                199,
                "/static/images/comedy_night.jpg",
                sched_comedy,
                4.9,
                34,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Acoustic Sunset Jam & Coffee Club",
                "Unwind with soulful acoustic indie covers, warm fairy lights, and freshly brewed pour-over coffee in a cozy rustic café atmosphere.",
                "Music",
                (now + timedelta(days=7)).strftime("%Y-%m-%d"),
                "18:00",
                "Third Wave Coffee Lounge, Koramangala",
                80,
                22000,
                11200,
                199,
                "/static/images/acoustic_jam.jpg",
                sched_music,
                4.8,
                29,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Midnight Rooftop Stargazing & Telescopes",
                "Gaze at the rings of Saturn, distant nebulae, and constellations through high-powered astronomical telescopes from a panoramic open-air city terrace.",
                "Experience",
                (now + timedelta(days=9)).strftime("%Y-%m-%d"),
                "21:00",
                "Skyline Terrace Lounge, MG Road",
                95,
                40000,
                21000,
                199,
                "/static/images/rooftop_stargazing.jpg",
                sched_stars,
                5.0,
                48,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Weekend Clay & Pottery Masterclass",
                "Get your hands messy and discover the therapeutic art of wheel-thrown pottery. Take home your own handcrafted ceramic vase or coffee mug!",
                "Workshop",
                (now + timedelta(days=14)).strftime("%Y-%m-%d"),
                "11:00",
                "The Clay Studio & Arts Guild, HSR Layout",
                45,
                30000,
                14500,
                299,
                "/static/images/pottery_craft.jpg",
                sched_pottery,
                4.9,
                22,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Echoes of Lumina: Electronic Music & Light Festival",
                "An immersive open-air electronic soundscape featuring international ambient & synthwave acts, volumetric laser projection mapping, and organic artisan food pop-ups.",
                "Music",
                (now + timedelta(days=28)).strftime("%Y-%m-%d"),
                "17:00",
                "Sunlit Meadows Amphitheater, Whitefield",
                1500,
                1200000,
                780000,
                499,
                "/static/images/music_festival.jpg",
                sched_music,
                4.9,
                64,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Global AI & NextTech Summit 2026",
                "The premier international gathering of AI researchers, enterprise architects, and founders exploring frontier LLMs, autonomous agents, and spatial intelligence.",
                "Technology",
                (now + timedelta(days=21)).strftime("%Y-%m-%d"),
                "09:30",
                "Bengaluru International Exhibition Centre, Hall 3",
                650,
                1500000,
                920000,
                499,
                "/static/images/ai_summit.jpg",
                sched_summit,
                5.0,
                82,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Founders & Angels: Venture Pitch Gala",
                "Curated matchmaking between 25 high-growth Series A startups and 60 leading venture funds, angels, and syndicate leads, concluding with a private dinner.",
                "Business",
                (now + timedelta(days=12)).strftime("%Y-%m-%d"),
                "18:00",
                "Grand Ballroom, The Oberoi Luxury Hotel",
                180,
                750000,
                480000,
                0,
                "/static/images/founders_gala.jpg",
                sched_summit,
                4.8,
                19,
                "published",
                now.isoformat()
            ),
            (
                demo_user_id,
                "Bengaluru AI Hackathon & Sprint 2026",
                "Build autonomous AI agents, fine-tune models, and ship production applications in a rapid 24-hour sprint with compute grants and mentor feedback.",
                "Technology",
                (now + timedelta(days=16)).strftime("%Y-%m-%d"),
                "10:00",
                "WeWork Galaxy Studio & Innovation Hub",
                200,
                150000,
                85000,
                199,
                "/static/images/ai_summit.jpg",
                sched_summit,
                4.9,
                38,
                "published",
                now.isoformat()
            )
        ]

        cursor.executemany("""
            INSERT INTO events (owner_id, title, description, category, date, start_time, venue, capacity, budget, expenses, ticket_price, banner_url, schedule_json, rating, review_count, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, events_data)

        e1_id = 1
        e2_id = 2
        e3_id = 3
        e4_id = 4

        # Demo Itemized Expenses for Event 1 (Comedy Night)
        expenses_data = [
            (e1_id, demo_user_id, "Comedian Appearance Fees", "Performers", 10000, (now - timedelta(days=2)).strftime("%Y-%m-%d"), now.isoformat()),
            (e1_id, demo_user_id, "Sound System & Mic Rental", "Audio/Visual", 4500, (now - timedelta(days=1)).strftime("%Y-%m-%d"), now.isoformat()),
            (e1_id, demo_user_id, "Social Media & Poster Ads", "Marketing", 2500, now.strftime("%Y-%m-%d"), now.isoformat()),
            (e1_id, demo_user_id, "Green Room Snacks & Beverages", "Catering", 1500, now.strftime("%Y-%m-%d"), now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO expenses (event_id, owner_id, title, category, amount, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, expenses_data)

        # Demo Reviews for Events
        reviews_data = [
            (e1_id, "Rohan Deshmukh", 5, "Unbelievable comedic timing! The host was super sharp and crowd work had us crying with laughter.", now.isoformat()),
            (e1_id, "Ananya Roy", 5, "Best ₹199 I've spent all month. Super cozy venue and incredible atmosphere.", now.isoformat()),
            (e2_id, "Kunal Bhatia", 5, "The acoustic sets were so chill and relaxing. Loved the coffee pairing too!", now.isoformat()),
            (e3_id, "Deepa Krishnan", 5, "Seeing Saturn's rings clearly through the rooftop telescope was magical. Highly recommended!", now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO reviews (event_id, author_name, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, reviews_data)

        # Demo Guests
        guests_data = [
            (e1_id, demo_user_id, "Priya Sundaram", "priya.ai@neurocloud.io", "accepted", now.isoformat()),
            (e1_id, demo_user_id, "Dr. Vikram Seth", "vseth@quantumsystems.org", "accepted", now.isoformat()),
            (e1_id, demo_user_id, "Elena Rostova", "elena@frontierlabs.co", "pending", now.isoformat()),
            (e1_id, demo_user_id, "Rohan Varma", "rohan@hypergrowth.vc", "declined", now.isoformat()),
            (e2_id, demo_user_id, "Kavita Nair", "kavita.beats@sonicwave.in", "accepted", now.isoformat()),
            (e3_id, demo_user_id, "David Chen", "dchen@sequoia-capital.example", "accepted", now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO guests (event_id, owner_id, name, email, rsvp, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, guests_data)

        # Demo Tasks
        tasks_data = [
            (e1_id, demo_user_id, "Sound-check wireless Shure SM58 microphones", "Dev Patel", (now + timedelta(days=2)).strftime("%Y-%m-%d"), "done", "high", now.isoformat()),
            (e1_id, demo_user_id, "Prepare VIP front-row seating & reserved tags", "Aisha Khan", (now + timedelta(days=3)).strftime("%Y-%m-%d"), "in_progress", "medium", now.isoformat()),
            (e1_id, demo_user_id, "Brief ticket scanner volunteers for gate entry", "Aarav Sharma", (now + timedelta(days=4)).strftime("%Y-%m-%d"), "todo", "high", now.isoformat()),
            (e2_id, demo_user_id, "Confirm acoustic DI boxes and amplifier patch cables", "Alex Rivera", (now + timedelta(days=5)).strftime("%Y-%m-%d"), "in_progress", "medium", now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO tasks (event_id, owner_id, title, assignee, due_date, status, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, tasks_data)

        # Demo Checklist
        checklist_data = [
            (e1_id, demo_user_id, "Brick wall stage spotlight focus and dimmer test", 1, now.isoformat()),
            (e1_id, demo_user_id, "Drink vouchers printed and bar counter stocked", 1, now.isoformat()),
            (e1_id, demo_user_id, "Entry QR scanner tablets charged and connected", 1, now.isoformat()),
            (e1_id, demo_user_id, "Artist green room hospitality basket delivered", 0, now.isoformat()),
            (e2_id, demo_user_id, "Coffee roasting equipment line check & beans prepared", 1, now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO checklist_items (event_id, owner_id, text, done, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, checklist_data)

        # Demo Registrations
        reg_data = [
            (e1_id, demo_user_id, "Sarah Jenkins", "sarah.j@deepmind.example", "EVT-8F29A10B", "Standard Pass (₹199)", 2, 398, (now - timedelta(hours=1)).isoformat(), now.isoformat()),
            (e1_id, demo_user_id, "Arjun Singhal", "arjun@zenithtech.io", "EVT-6B92C44D", "Standard Pass (₹199)", 1, 199, None, now.isoformat()),
            (e1_id, demo_user_id, "Meera Krishnan", "meera.k@startupgrowth.in", "EVT-1E48D77A", "Early Bird (₹149)", 2, 298, None, now.isoformat()),
            (e2_id, demo_user_id, "Rahul Bose", "rahul.bose@electro.fm", "EVT-9A33F55E", "Standard Pass (₹199)", 1, 199, None, now.isoformat()),
            (e3_id, demo_user_id, "Tanya Mehra", "tanya@stargaze.club", "EVT-4C77E21B", "Standard Pass (₹199)", 2, 398, None, now.isoformat())
        ]
        cursor.executemany("""
            INSERT INTO registrations (event_id, owner_id, attendee_name, attendee_email, ticket_id, ticket_tier, quantity, total_amount, checked_in_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, reg_data)

        # Demo Notifications
        notif_data = [
            (demo_user_id, e1_id, "Welcome to Evntra! Your 8 events and live ticket booking engine are active.", None, now.isoformat()),
            (demo_user_id, e1_id, 'Sarah Jenkins booked 2 tickets (₹398) for "Friday Night Standup Comedy Lounge".', None, (now - timedelta(minutes=30)).isoformat()),
            (demo_user_id, e1_id, 'Ticket check-in completed: Sarah Jenkins scanned at Gate Entry #1.', None, (now - timedelta(minutes=15)).isoformat())
        ]
        cursor.executemany("""
            INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, notif_data)

        conn.commit()
        print("✓ Rich demo dataset with ₹199 events, itemized expenses, and reviews successfully seeded into SQLite database.")

    conn.close()

if __name__ == "__main__":
    init_db(force_reseed=True)
