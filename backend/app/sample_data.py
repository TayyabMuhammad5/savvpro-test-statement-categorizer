from __future__ import annotations

from typing import Dict

# Synthetic, realistic messy bank/credit card statements for an independent
# Editorial Photographer & Fine-Art Photobook Publisher ("Aperture & Spine Studio")
# Strictly fake data — no real personal details or real account numbers.

CHASE_STUDIO_CREDIT_CARD_CSV = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
03/02/2025,03/03/2025,B&H PHOTO 800-606-6969 NY,Shopping,Sale,-3299.00,Medium Format 80mm Lens & Profoto B10X Strobe
03/04/2025,03/05/2025,LENSRENTALS.COM 901-754-9100 TN,Services,Sale,-485.00,Tilt-Shift Lens Rental - Architecture Book Shoot
03/05/2025,03/05/2025,LENSRENTALS.COM PENDING AUTH HOLD,Services,Sale,-485.00,PENDING pre-authorization hold
03/08/2025,03/09/2025,LENSRENTALS.COM DEPOSIT RETURN,Services,Return,150.00,Security deposit release & weekend return credit
03/10/2025,03/11/2025,BLURB *BOOK PRINT RUN SAN FRANCISCO CA,Printing,Sale,-1420.50,150x Hardcover Monograph Proof & Short-Run Bindery
03/12/2025,03/13/2025,BLURB *DEFECT CREDIT SAN FRANCISCO CA,Printing,Return,180.00,Credit for 18 scuffed dust jackets in batch #402
03/14/2025,03/14/2025,ADOBE *PHOTOGRAPHY PLAN 800-833-6687 CA,Software,Sale,-59.99,Lightroom + Photoshop + InDesign Creative Cloud
03/15/2025,03/15/2025,CAPTURE ONE PRO SUBSCRIPTION COPENHAGEN,Software,Sale,-24.00,Tethered RAW studio capture license
03/15/2025,03/15/2025,FOREIGN TRANSACTION FEE CAPTURE ONE,Fees,Fee,-0.72,3% Intl card processing fee
03/17/2025,03/18/2025,PIXIESET CLIENT GALLERY VANCOUVER,Software,Sale,-38.00,Client proofing & fine art print fulfillment store
03/19/2025,03/20/2025,PEERSPACE *DAYLIGHT LOFT BROOKLYN NY,Rent,Sale,-640.00,8hr Editorial Portrait & Author Book Jacket Shoot
03/20/2025,03/20/2025,EZCATER*SHOOT CREW LUNCH BROOKLYN NY,Food & Drink,Sale,-218.40,Catering for 6 crew members + publisher art director
03/21/2025,03/22/2025,JOES CAFE 9921 BROOKLYN NY,Food & Drink,Sale,-18.75,Morning espresso & pastry
03/22/2025,03/23/2025,UBER *TRIP HELP.UBER.COM,Travel,Sale,-46.80,Ride with pelican cases to Pier 59 Studios
03/24/2025,03/25/2025,STRAND BOOK STORE 828 BROADWAY NY,Books,Sale,-195.00,Rare Japanese photobook monographs for layout reference
03/25/2025,03/26/2025,MILLERS PRO LAB PITTSBURG KS,Printing,Sale,-312.80,Archival silver gelatin & baryta exhibition prints
03/26/2025,03/27/2025,USPS PO 350892 BROOKLYN NY,Shipping,Sale,-164.20,Media Mail & Priority shipping for pre-ordered photobooks
03/27/2025,03/28/2025,ULINE *BOOK MAILERS 800-295-5510 WI,Supplies,Sale,-245.00,200x rigid corrugated book wraps & archival sleeves
03/28/2025,03/28/2025,AMAZON.COM*MKTPL 8821WA SEATTLE WA,Shopping,Sale,-142.65,Order #114-9920182
03/29/2025,03/29/2025,TARGET 0001842 BROOKLYN NY,Shopping,Sale,-89.40,POS Debit 4491
03/30/2025,03/30/2025,VENMO *MARCUS VANCE,Personal,Sale,-250.00,Transfer memo: Saturday shoot
03/31/2025,03/31/2025,AUTOMATIC PAYMENT - THANK YOU,Payment,Payment,4500.00,Monthly statement autopay from checking
"""

AMEX_EDITORIAL_SHOOT_CSV = """Account: Amex Business Gold - Card Ending 81004 (Fake Statement Export)
Statement Period: 2025-04-01 to 2025-04-30
Date,Description,Charge Amount,Type,Status,Extended Details
2025-04-02,DELTA AIR LINES ATLANTA GA,$618.40,Charge,Posted,Roundtrip JFK-LAX for LA Art Book Fair & Editorial Assignment
2025-04-03,ACE HOTEL DOWNTOWN LOS ANGELES CA,$892.00,Charge,Posted,3 nights lodging during LA Art Book Fair
2025-04-04,LA ART BOOK FAIR EXHIBITOR BOOTH,$750.00,Charge,Posted,Exhibitor table at Geffen Contemporary for monograph launch
2025-04-05,INDIE FILM LAB MONTGOMERY AL,$284.00,Charge,Posted,18 rolls Portra 400 120 medium format C-41 dev + Noritsu scans
2025-04-05,INDIE FILM LAB MONTGOMERY AL,$284.00,Charge,Posted,Duplicate import of same-day lab batch
2025-04-08,INGRAMSPARK PRINT DISTRIBUTION LAVERGNE TN,$149.00,Charge,Posted,Global book distribution setup & proof run
2025-04-10,BOWKER ISBN MYIDENTIFIERS.COM NEW PROVIDENCE NJ,$295.00,Charge,Posted,Block of 10 ISBNs + barcodes for studio photobook imprint
2025-04-12,HISCOX BUSINESS INSURANCE ATLANTA GA,$94.50,Charge,Posted,Monthly commercial liability & inland marine camera policy
2025-04-14,ADORAMA INC 212-741-0401 NY,$429.00,Charge,Posted,Godox V1 Pro Flash + MagMod Diffuser Kit
2025-04-16,ADORAMA INC RETURN CREDIT NY,-$79.00,Credit,Posted,Returned defective flash battery pack
2025-04-18,ARCANA BOOKS ON THE ARTS CULVER CITY CA,$168.00,Charge,Posted,Reference monographs & bookbinding specimen catalog
2025-04-20,TST* BLUE BOTTLE COFFEE LOS ANGELES CA,$24.50,Charge,Posted,Coffee & oat latte
2025-04-22,APPLE.COM/BILL 866-712-7753 CA,$29.99,Charge,Posted,Monthly billing - unknown subscription or personal family plan
2025-04-25,AMEX EPAYMENT ACH PMT,-$2500.00,Payment,Posted,Online payment received - thank you
"""

MERCURY_STUDIO_CHECKING_CSV = """Date,Description,Debit,Credit,Status,Reference
2025-05-01,HONEYBOOK*CLIENT PAYOUT - WEDDING & ALBUM PKG,,4850.00,Posted,Editorial Wedding + Custom Linen Heirloom Book Retainer
2025-05-03,PIXIESET*PRINT STORE PAYOUT,,1640.00,Posted,Limited Edition Monograph & Fine Art Print Store Payout
2025-05-05,BLURB*AUTHOR ROYALTY PAYOUT,,612.50,Posted,Q1 Photobook Trade Distribution Royalties
2025-05-07,EDITION ONE BOOKS BERKELEY CA,2890.00,,Posted,50% Deposit - 250 copies Smyth-sewn clothbound photobook
2025-05-09,PIRATESHIP POSTAGE & FULFILLMENT,214.60,,Posted,Batch shipping labels for book club subscribers
2025-05-11,BROOKLYN DARKROOM MEMBERSHIP,195.00,,Posted,Monthly 4x5 enlarger & fiber print darkroom access
2025-05-13,US COPYRIGHT OFFICE WASHINGTON DC,65.00,,Posted,Group registration of published photographs (VA)
2025-05-15,ONLINE TRANSFER TO SAVINGS,2000.00,,Posted,Tax reserve transfer to high-yield studio savings
2025-05-17,OWNER DRAW ACH TRANSFER TO SELF,3500.00,,Posted,Monthly sole proprietor draw
2025-05-19,B&H PHOTO REFUND OVERPAYMENT,,124.00,Posted,Sales tax exemption adjustment credit on paper stock
2025-05-21,PAYPAL *KATE STYLING,450.00,,Posted,P2P transfer - no invoice code attached
2025-05-23,CHECK DEPOSIT #1084,,1200.00,Posted,Mobile check deposit - memo illegible
2025-05-25,ATM WITHDRAWAL CHASE 11201,160.00,,Posted,Cash withdrawal before flea market prop hunt
"""

SAMPLE_STATEMENTS: Dict[str, Dict[str, str]] = {
    "chase_studio_card": {
        "id": "chase_studio_card",
        "name": "Chase Ink Studio Card (Signed Single-Column CSV)",
        "filename": "chase_studio_credit_card_2025.csv",
        "description": "22 rows: B&H Section 179 lens ($3,299), LensRentals pending hold + security deposit refund, Blurb book printing + defect credit, Capture One + 3% FX fee, PeerSpace loft, EzCater crew lunch, Strand Books, Amazon/Target/Venmo/Joe's Cafe review traps, and Autopay.",
        "csv": CHASE_STUDIO_CREDIT_CARD_CSV.strip(),
    },
    "amex_editorial_shoot": {
        "id": "amex_editorial_shoot",
        "name": "Amex Business Gold — LA Art Book Fair & Shoot (Positive-Charge CSV + Preamble)",
        "filename": "amex_editorial_shoot_2025.csv",
        "description": "14 rows with 2 metadata preamble lines and inverted positive-charge convention: Delta airfare, Ace Hotel, LA Art Book Fair booth, Indie Film Lab duplicate row, IngramSpark, Bowker ISBNs, Adorama gear + return credit, Blue Bottle & Apple.com traps.",
        "csv": AMEX_EDITORIAL_SHOOT_CSV.strip(),
    },
    "mercury_studio_checking": {
        "id": "mercury_studio_checking",
        "name": "Mercury Studio Checking (Split Debit/Credit Columns CSV)",
        "filename": "mercury_studio_checking_2025.csv",
        "description": "13 rows with separate Debit/Credit columns: HoneyBook client shoot payouts, Pixieset & Blurb book royalties, Edition One Books bindery, Brooklyn Darkroom, B&H tax refund credit, Owner Draw, Transfer to Savings, plus unverified Check Deposit & ATM cash traps.",
        "csv": MERCURY_STUDIO_CHECKING_CSV.strip(),
    },
}
