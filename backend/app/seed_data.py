"""Catalogue used by the seed generator: realistic objects, places and wording.

A "story" is one physical object that may be reported lost by its owner AND found by
somebody else. The two reports describe it in different words (and sometimes with
different photos), which is exactly what the matching engine has to bridge."""

LOCATIONS = [
    # name, campus, building, floor, lat, lon (approximate positions on the RR campus)
    ("MRD Block (Silver Jubilee Block)", "RR Campus", "MRD Block", None, 12.93450, 77.53450),
    ("GJB Block (Golden Jubilee Block)", "RR Campus", "GJB Block", None, 12.93458, 77.53505),
    ("BE Block", "RR Campus", "BE Block", None, 12.93466, 77.53560),
    ("F Block (Panini Block)", "RR Campus", "F Block", None, 12.93450, 77.53615),
    ("Tech Center", "RR Campus", "Tech Center", None, 12.93458, 77.53670),
    ("Architecture Block", "RR Campus", "Architecture Block", None, 12.93466, 77.53725),
    ("Central Library", "RR Campus", "Central Library", None, 12.93495, 77.53450),
    ("Hornbill", "RR Campus", "Hornbill", None, 12.93503, 77.53505),
    ("GJB Canteen", "RR Campus", "GJB Block", None, 12.93511, 77.53560),
    ("13th Floor Cafeteria", "RR Campus", "GJB Block", None, 12.93495, 77.53615),
    ("CCD Express", "RR Campus", None, None, 12.93503, 77.53670),
    ("Hostel Food Court & Messes", "RR Campus", "Hostels", None, 12.93511, 77.53725),
    ("Campus Mart", "RR Campus", None, None, 12.93540, 77.53450),
    ("Sutta Gully", "RR Campus", None, None, 12.93548, 77.53505),
    ("Main Sports Ground", "RR Campus", "Sports Facilities", None, 12.93556, 77.53560),
    ("GJB Indoor Sports Courts", "RR Campus", "GJB Block", None, 12.93540, 77.53615),
    ("Two-Storey Campus Gym", "RR Campus", "Sports Facilities", None, 12.93548, 77.53670),
    ("MRD Auditorium", "RR Campus", "MRD Block", None, 12.93556, 77.53725),
    ("Jag's Nest", "RR Campus", None, None, 12.93585, 77.53450),
    ("Sol Sac", "RR Campus", None, None, 12.93593, 77.53505),
    ("Center for Excellence (CoE)", "RR Campus", "CoE", None, 12.93601, 77.53560),
    ("BE Block Stores", "RR Campus", "BE Block", None, 12.93585, 77.53615),
    ("Boys Hostel", "RR Campus", "Hostels", None, 12.93593, 77.53670),
    ("Girls Hostel", "RR Campus", "Hostels", None, 12.93601, 77.53725),
]

COLORS = ["black", "blue", "red", "green", "grey", "white", "brown", "silver", "pink", "navy", "yellow", "purple"]
RGB = {"black": (25, 25, 28), "blue": (40, 90, 200), "red": (200, 35, 40), "green": (45, 150, 70),
       "grey": (130, 130, 135), "white": (240, 240, 240), "brown": (120, 75, 40), "silver": (190, 195, 205),
       "pink": (235, 130, 170), "navy": (25, 35, 100), "yellow": (240, 200, 40), "purple": (120, 60, 160),
       "gold": (212, 175, 55)}

# category, noun, shape (for image rendering), brands, colour pool or None, feature pairs (lost wording, found wording)
OBJECTS = [
    ("electronics", "phone", "phone", ["iPhone 14", "Samsung Galaxy", "Google Pixel", "OnePlus"], None, [
        ("The screen has a crack in the top left corner.", "Cracked screen, mostly on the upper left side."),
        ("It is in a clear case with a pop socket on the back.", "Transparent case with a pop socket attached."),
        ("It has a photo of a golden retriever as the lock screen.", "Lock screen shows a golden retriever puppy."),
        ("There is a small sticker of a mountain on the case.", "A mountain sticker is stuck on the back cover.")]),
    ("electronics", "laptop", "laptop", ["Dell XPS", "HP Pavilion", "Lenovo ThinkPad", "MacBook Air"], ["silver", "black", "grey"], [
        ("The lid is covered in programming stickers.", "Lots of stickers on the lid, mostly coding logos."),
        ("It was in a grey padded sleeve with my name tag.", "Found inside a grey neoprene sleeve with a name tag."),
        ("It has a dent on the left corner and a Linux sticker.", "Small dent on one corner, penguin sticker on the cover.")]),
    ("electronics", "earbuds", "earbuds", ["AirPods Pro", "Sony WF-1000XM4", "Galaxy Buds"], ["white", "black"], [
        ("They are in a charging case with a red keychain clip.", "Charging case with a red carabiner clip attached."),
        ("The case has a scratch along the front.", "Scratched front on the case, one earbud slightly yellowed.")]),
    ("electronics", "headphones", "headphones", ["Bose QuietComfort", "Sony WH-1000XM5", "JBL"], ["black", "silver", "blue"], [
        ("Over-ear with a cracked left ear pad.", "Over-ear model, the left ear cushion is torn."),
        ("Comes with a hard travel case.", "Was inside a zip-up travel case.")]),
    ("electronics", "calculator", "calculator", ["Casio fx-991", "Texas Instruments TI-84"], ["black", "grey"], [
        ("My initials are scratched on the back.", "Initials carved into the back cover."),
        ("The cover slides off and is missing.", "No slide cover, a few worn keys.")]),
    ("electronics", "smartwatch", "watch", ["Apple Watch", "Fitbit Versa", "Garmin Forerunner"], ["black", "pink", "navy"], [
        ("It has a green sport band and a cracked glass.", "Green silicone band, glass has a small crack."),
        ("The charger cable was clipped to it.", "Found with its magnetic charger cable still attached.")]),
    ("electronics", "power bank", "box", ["Anker", "Xiaomi", "Belkin"], ["black", "white", "blue"], [
        ("Slim 10000 mAh with a USB-C cable wrapped around.", "Thin battery pack with a short USB-C cable tied to it.")]),
    ("wallet_bag", "wallet", "wallet", ["Fossil", "Tommy Hilfiger", "Levi's", "Coach"], ["black", "brown", "navy"], [
        ("It has my student card, a bus pass and some cash.", "Contains a student card, bus pass and a few bills."),
        ("Bi-fold with a broken zipper on the coin pocket.", "Folding wallet, coin pocket zipper is stuck."),
        ("There is a photo of a baby in the clear window.", "A small baby photo in the ID window.")]),
    ("wallet_bag", "backpack", "backpack", ["JanSport", "The North Face", "Nike", "Herschel", "Osprey"], None, [
        ("It has a keychain of a small plush panda on the zip.", "Panda plush keychain hanging from the main zipper."),
        ("Inside are two textbooks and a pencil case.", "Held a couple of textbooks and a pencil case."),
        ("The front pocket has a torn seam.", "Ripped stitching on the front pocket.")]),
    ("wallet_bag", "handbag", "handbag", ["Michael Kors", "Kate Spade", "Zara"], ["black", "brown", "red", "pink"], [
        ("Gold chain strap and a magnetic clasp.", "Chain strap with a magnetic snap closure."),
        ("Contains makeup bag and a set of house keys.", "Has a make-up pouch and keys inside.")]),
    ("wallet_bag", "laptop bag", "backpack", ["Targus", "Samsonite", "Dell"], ["black", "grey", "navy"], [
        ("Padded shoulder strap and a luggage tag with my name.", "Shoulder bag with a luggage tag attached.")]),
    ("keys", "car key", "key", ["Toyota", "Honda", "Ford", "Volkswagen"], ["black", "silver"], [
        ("Fob has a bottle opener keyring and two small keys.", "Remote fob attached to a bottle opener and two brass keys."),
        ("The rubber cover is worn and the lock button is missing.", "Rubber fob cover is worn, one button gone.")]),
    ("keys", "house keys", "key", [None], ["silver", "gold"], [
        ("Three keys on a red lanyard with a tiny flashlight.", "Three keys on a red lanyard and a mini torch."),
        ("There is a green tag that says room 214.", "Green plastic tag marked 214 on the ring.")]),
    ("keys", "bike lock key", "key", [None], ["silver", "black"], [
        ("Small key with an orange rubber cap.", "Little key, orange plastic head.")]),
    ("id_card", "student ID card", "card", ["University"], ["white", "blue"], [
        ("It is in a clear plastic holder with a lanyard.", "Card in a plastic sleeve, blue lanyard."),
        ("The card shows a photo of me with a beard.", "Photo of a bearded man on the card.")]),
    ("id_card", "driver's licence", "card", [None], ["white"], [
        ("Issued last year and kept in a leather card slip.", "Found in a brown leather card holder.")]),
    ("id_card", "bus pass", "card", ["City Transit"], ["green", "blue"], [
        ("Monthly pass with my name printed on it.", "Monthly transit pass, a name is printed on the front.")]),
    ("clothing", "jacket", "jacket", ["Columbia", "Patagonia", "Uniqlo", "Adidas"], None, [
        ("Zip pockets, there is a hand warmer in the left one.", "Zippered pockets; a hand warmer is still inside."),
        ("The hood has a small tear and the lining is red.", "Hood has a tiny rip, red lining inside.")]),
    ("clothing", "hoodie", "jacket", ["Champion", "Nike", "H&M"], None, [
        ("It has the university logo on the chest.", "University crest printed on the front."),
        ("Size medium, a coffee stain near the cuff.", "Medium size with a faint stain on one sleeve.")]),
    ("clothing", "scarf", "scarf", ["Burberry", None], ["red", "grey", "navy", "green"], [
        ("Wool scarf with a checked pattern and fringe.", "Knitted checked scarf with tassels.")]),
    ("clothing", "gloves", "scarf", ["North Face", None], ["black", "grey", "navy"], [
        ("A pair of leather gloves, wool lined.", "Leather gloves with a soft lining.")]),
    ("jewelry", "ring", "ring", [None, "Pandora"], ["silver", "gold"], [
        ("A thin band with a small blue stone.", "Slim ring with a tiny blue gem."),
        ("There is an engraving on the inside of the band.", "Inscription engraved inside.")]),
    ("jewelry", "necklace", "ring", ["Pandora", None], ["silver", "gold"], [
        ("Delicate chain with a heart pendant.", "Fine chain and a small heart charm.")]),
    ("jewelry", "wristwatch", "watch", ["Casio", "Seiko", "Fossil", "Timex"], ["silver", "black", "gold"], [
        ("Metal strap, the face has a date window.", "Steel bracelet and a date display.")]),
    ("jewelry", "bracelet", "ring", [None], ["silver", "gold", "brown"], [
        ("A woven bracelet with a few small charms.", "Braided bracelet with charms.")]),
    ("documents", "notebook", "book", ["Moleskine", "Leuchtturm", None], None, [
        ("Full of lecture notes with a coffee ring on the cover.", "Lecture notes inside and a coffee ring on the cover."),
        ("Name written on the first page.", "A name is written inside the front cover.")]),
    ("documents", "textbook", "book", ["Pearson", "O'Reilly", "Wiley"], ["blue", "red", "green"], [
        ("Calculus textbook with highlighted chapters.", "Maths textbook, lots of yellow highlighter."),
        ("Has a library bookmark and sticky notes.", "Bookmark and sticky tabs sticking out.")]),
    ("documents", "folder", "book", [None], ["blue", "red", "grey"], [
        ("Plastic folder with printed project reports.", "Contains printed reports and a signed form.")]),
    ("other", "water bottle", "bottle", ["Hydro Flask", "Nalgene", "Yeti", "Contigo"], None, [
        ("Stainless steel with lots of stickers and a dent at the bottom.", "Steel bottle with stickers, dented base."),
        ("The lid is attached by a green strap.", "Lid has a green strap loop.")]),
    ("other", "umbrella", "umbrella", [None, "Totes"], ["black", "navy", "red", "green", "yellow"], [
        ("Automatic umbrella with a wooden handle.", "Folding umbrella, wooden hook handle."),
        ("One of the ribs is bent.", "Bent rib on one side.")]),
    ("other", "sunglasses", "glasses", ["Ray-Ban", "Oakley", None], ["black", "brown", "silver"], [
        ("Aviator style in a hard case.", "Aviators, found with their hard case."),
        ("A small scratch on the left lens.", "Left lens slightly scratched.")]),
    ("other", "glasses", "glasses", [None], ["black", "brown", "silver", "blue"], [
        ("Prescription glasses with thin frames.", "Wire framed prescription glasses."),
        ("Came in a soft blue pouch.", "In a blue microfibre pouch.")]),
    ("other", "lunch box", "box", ["Tupperware", None], ["blue", "pink", "green", "grey"], [
        ("Contains a fork and a spoon.", "Has cutlery tucked inside.")]),
    ("other", "bike helmet", "helmet", ["Giro", "Bell", None], None, [
        ("Has a flashing LED on the back and a scratch on the right.", "Rear LED light, scuffed on one side.")]),
    ("pet", "cat", None, [None], ["grey", "brown", "black", "white"], [
        ("A friendly tabby wearing a green collar with a bell.", "Friendly tabby cat with a green collar and a bell."),
        ("She is microchipped and answers to Mila.", "Has a microchip, calm and used to people.")]),
    ("pet", "dog", None, [None], ["brown", "black", "white", "grey"], [
        ("A small terrier mix with a blue harness.", "Small terrier type wearing a blue harness."),
        ("He is shy and has a white patch on his chest.", "Timid, white chest patch.")]),
]

LOST_OPENERS = [
    "I lost my {adj}{noun}{where}.", "Missing: {adj}{noun}. Last seen{where}.",
    "Lost my {adj}{noun}{where}, please help.", "Can anyone help? I left my {adj}{noun}{where}.",
]
FOUND_OPENERS = [
    "Found a {adj}{noun}{where}.", "Handed in: a {adj}{noun} picked up{where}.",
    "Someone left a {adj}{noun}{where}.", "Found this {adj}{noun}{where}, looking for the owner.",
]
FOUND_CLOSERS = ["Kept safe at the front desk.", "Please describe it to claim.", "Currently with campus security.", ""]
LOST_CLOSERS = ["Reward offered.", "It has sentimental value.", "Thank you!", ""]

EXTRAS = {
    "electronics": lambda r: {"serial_number": "".join(r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(10)),
                              "imei_last4": str(r.randint(1000, 9999))},
    "id_card": lambda r: {"card_type": r.choice(["student", "driver licence", "transit pass", "library"]),
                          "name_visible": r.choice([True, False])},
    "pet": lambda r: {"species": None, "breed": r.choice(["tabby", "terrier mix", "labrador", "siamese", "unknown"]),
                      "microchipped": r.choice([True, False])},
    "keys": lambda r: {"key_count": r.randint(1, 6), "has_fob": r.choice([True, False])},
    "wallet_bag": lambda r: {"contains_cards": r.choice([True, False]), "contains_cash": r.choice([True, False])},
}

# Distinguishing details: real owners almost always remember one. Without them two black
# backpacks are indistinguishable, which would make precision on the demo data meaningless.
DETAIL_WORDS = ["panda", "dragon", "eagle", "lighthouse", "pineapple", "rocket", "violin", "cactus", "anchor", "moon",
                "dolphin", "tulip", "castle", "compass", "owl", "mushroom", "kite", "comet", "lantern", "maple leaf",
                "chess knight", "football", "guitar", "sunflower", "tiger", "whale", "mountain", "cherry", "bicycle", "fox"]
DETAIL_TEMPLATES = [
    ("It has a small {w} sticker on it.", "There is a little {w} sticker on it."),
    ("A {w} charm is attached to it.", "A {w} charm hangs from it."),
    ("It is marked with a {w} drawn in marker.", "Someone drew a {w} on it in marker."),
    ("There is a {w} pattern on one side.", "One side shows a {w} design."),
]
INITIALS = ["A.K.", "J.M.", "R.S.", "T.P.", "L.D.", "M.H.", "S.B.", "C.W.", "N.F.", "E.G."]
