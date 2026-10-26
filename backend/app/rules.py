from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern, Tuple
from .models import TaxCategory, TaxFlag, TransactionType


SCHEDULE_C_MAPPING: Dict[TaxCategory, Tuple[str, float]] = {
    TaxCategory.GEAR_RENTALS: ("Line 20a — Rent/Lease Vehicles, Machinery & Equipment", 1.0),
    TaxCategory.CAMERA_EQUIPMENT: ("Line 13 / Line 22 — Section 179 Equipment & Supplies", 1.0),
    TaxCategory.PHOTOBOOK_PRINTING: ("Part III Line 38 — Cost of Goods Sold (Print & Bindery)", 1.0),
    TaxCategory.SOFTWARE_WORKFLOW: ("Line 18 — Office & Digital Workflow Subscriptions", 1.0),
    TaxCategory.STUDIO_LOCATIONS: ("Line 20b — Studio, Darkroom & Shoot Location Permits", 1.0),
    TaxCategory.TRAVEL_TRANSPORT: ("Line 24a — Shoot Travel, Airfare, Lodging & Transit", 1.0),
    TaxCategory.SHIPPING_PACKAGING: ("Line 18 / COGS — Book Fulfillment, Mailers & Postage", 1.0),
    TaxCategory.PROPS_REFERENCE_BOOKS: ("Line 22 — Set Props, Styling & Photo Reference Books", 1.0),
    TaxCategory.CLIENT_CREW_MEALS: ("Line 24b — Deductible Client & Shoot Crew Meals (50%)", 0.5),
    TaxCategory.MARKETING_BOOK_FAIRS: ("Line 8 — Advertising, Portfolio & Art Book Fair Booths", 1.0),
    TaxCategory.INSURANCE_LEGAL: ("Line 15 / Line 17 — Gear Insurance, Copyright & Guilds", 1.0),
    TaxCategory.BANK_MERCHANT_FEES: ("Line 10 / Line 27a — Merchant Processing & FX Fees", 1.0),
    TaxCategory.CLIENT_BOOK_INCOME: ("Part I Line 1 — Gross Receipts (Shoots & Book Sales)", 0.0),
    TaxCategory.NON_DEDUCTIBLE_TRANSFER: ("Excluded — Internal Transfer / Credit Card Payment", 0.0),
    TaxCategory.PERSONAL_NON_DEDUCTIBLE: ("Excluded — Personal / Non-Deductible Expense", 0.0),
    TaxCategory.NEEDS_REVIEW: ("Pending — Requires Photographer Verification", 0.0),
}


@dataclass(frozen=True)
class MerchantRule:
    rule_id: str
    pattern: Pattern[str]
    category: TaxCategory
    base_confidence: float
    explanation: str
    default_type: TransactionType = TransactionType.EXPENSE
    tax_flag: TaxFlag = TaxFlag.NONE


@dataclass(frozen=True)
class AmbiguityTrap:
    trap_id: str
    pattern: Pattern[str]
    max_confidence: float
    reason: str
    suggested_categories: List[TaxCategory] = field(default_factory=list)
    tax_flag: TaxFlag = TaxFlag.OPAQUE_MERCHANT


# ---------------------------------------------------------------------------
# Layer 1: Non-Expense / Transfer & Bill Payment Rules
# ---------------------------------------------------------------------------
TRANSFER_RULES: List[MerchantRule] = [
    MerchantRule(
        rule_id="XFER_AUTOPAY",
        pattern=re.compile(r"\b(AUTOMATIC PAYMENT|AUTOPAY|PAYMENT THANK YOU|MOBILE PYMT|EPAYMENT|CREDIT CRD EPAY|ONLINE PAYMENT THANK YOU)\b", re.I),
        category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
        base_confidence=0.98,
        explanation="Credit card balance payment — internal liability settlement, not a deductible expense or taxable income.",
        default_type=TransactionType.TRANSFER,
        tax_flag=TaxFlag.INTERNAL_TRANSFER,
    ),
    MerchantRule(
        rule_id="XFER_SAVINGS_DRAW",
        pattern=re.compile(r"\b(TRANSFER TO SAVINGS|TRANSFER FROM SAVINGS|TRANSFER TO CHECKING|ONLINE TRANSFER|ACH TRANSFER TO SELF|OWNER DRAW|MEMBER DRAW|ZELLE TO SELF)\b", re.I),
        category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
        base_confidence=0.97,
        explanation="Internal account transfer or owner draw — movement between own accounts does not affect Schedule C net profit.",
        default_type=TransactionType.TRANSFER,
        tax_flag=TaxFlag.INTERNAL_TRANSFER,
    ),
    MerchantRule(
        rule_id="XFER_TAX_PAYMENT",
        pattern=re.compile(r"\b(IRS\s*USATAXPYMT|EFTPS|FRANCHISE TAX BOARD|NYS DTF PIT)\b", re.I),
        category=TaxCategory.NON_DEDUCTIBLE_TRANSFER,
        base_confidence=0.95,
        explanation="Federal/state estimated income tax payment — personal tax remittance is non-deductible on Schedule C.",
        default_type=TransactionType.TRANSFER,
        tax_flag=TaxFlag.INTERNAL_TRANSFER,
    ),
]


# ---------------------------------------------------------------------------
# Layer 2: Curated Domain Merchant Rules (Photography & Photobook Studio)
# Note: Dual-role platforms (HoneyBook, Pixieset, Blurb) evaluate explicit
# client payout / book royalty patterns first before SaaS/printing expenses.
# ---------------------------------------------------------------------------
MERCHANT_RULES: List[MerchantRule] = [
    # --- Client Shoot & Photobook Sales Income (Must evaluate before SaaS/Print rules) ---
    MerchantRule(
        rule_id="INC_CLIENT_PAYOUTS",
        pattern=re.compile(r"\b(HONEYBOOK\s*\*?\s*(?:CLIENT\s*)?PAYOUT|STRIPE\s*\*?\s*TRANSFER|SQUAREUP\s*\*?\s*BOOK|PIXIESET\s*\*?\s*(?:PRINT\s*)?STORE\s*PAYOUT|PIC-TIME\s*\*?\s*PAYOUT|BLURB\s*\*?\s*(?:AUTHOR\s*)?ROYALTY|INGRAM\s*CONTENT\s*ROYALTY|COND[EÉ]\s*NAST\s*AP|VOGUE\s*EDITORIAL\s*FEE|HARPERCOLLINS\s*PHOTO|CHRONICLE\s*BOOKS\s*ROYALTY|CHECK\s*DEPOSIT\s*CLIENT)\b", re.I),
        category=TaxCategory.CLIENT_BOOK_INCOME,
        base_confidence=0.96,
        explanation="Gross business revenue from photography commissions, print gallery sales, or photobook royalties.",
        default_type=TransactionType.INCOME,
    ),

    # --- Bank & Merchant Processing Fees (Must evaluate before software names like Capture One) ---
    MerchantRule(
        rule_id="FEES_FX_WIRE",
        pattern=re.compile(r"\b(FOREIGN\s*TRANSACTION\s*FEE|INTL\s*TRANSACTION\s*FEE|INTERNATIONAL\s*SERVICE\s*FEE|WIRE\s*TRANSFER\s*FEE|MONTHLY\s*MAINTENANCE\s*FEE|STRIPE\s*FEE)\b", re.I),
        category=TaxCategory.BANK_MERCHANT_FEES,
        base_confidence=0.95,
        explanation="Deductible business banking, wire, or foreign shoot currency conversion fee.",
    ),

    # --- Gear & Lens Rentals ---
    MerchantRule(
        rule_id="RENT_LENSRENTALS",
        pattern=re.compile(r"\b(LENSRENTALS|LENS\s*RENTALS|BORROWLENSES|SHAREGRID|ADORAMA\s*RENTAL|SAMYS\s*RENTAL|FOTOCARE\s*RENTAL|CSI\s*RENTALS)\b", re.I),
        category=TaxCategory.GEAR_RENTALS,
        base_confidence=0.96,
        explanation="Camera body, lens, or lighting rental house for client/editorial shoots (Schedule C Line 20a).",
    ),

    # --- Camera Equipment & Lighting ---
    MerchantRule(
        rule_id="GEAR_BH_ADORAMA",
        pattern=re.compile(r"\b(B&H\s*PHOTO|BH\s*PHOTO|B\s*&\s*H\s*PHOTO|ADORAMA(?!\s*RENTAL)|KEH\s*CAMERA|MPB\.COM|MPB\s*US|LEICA\s*CAMERA|LEICA\s*STORE|SAMYS\s*CAMERA)\b", re.I),
        category=TaxCategory.CAMERA_EQUIPMENT,
        base_confidence=0.94,
        explanation="Specialist camera, lens, and studio hardware vendor.",
    ),
    MerchantRule(
        rule_id="GEAR_LIGHTING_SUPPORT",
        pattern=re.compile(r"\b(PROFOTO|GODOX|APUTURE|NANLITE|PEAK\s*DESIGN|MANFROTTO|GITZO|REALLY\s*RIGHT\s*STUFF|PELICAN\s*CASES|THINK\s*TANK\s*PHOTO|TETHER\s*TOOLS|SEKONIC)\b", re.I),
        category=TaxCategory.CAMERA_EQUIPMENT,
        base_confidence=0.95,
        explanation="Professional studio lighting, tethering, tripod, or protective transport hardware.",
    ),

    # --- Photobook Printing & Fine-Art Lab COGS ---
    MerchantRule(
        rule_id="PRINT_PHOTOBOOK_PRESS",
        pattern=re.compile(r"\b(BLURB(?!\s*\*?\s*(?:AUTHOR\s*)?ROYALTY)|ARTIFACT\s*UPRISING|INGRAMSPARK|INGRAM\s*SPARK|LULU\s*PRESS|BOOKBABY|EDITION\s*ONE\s*BOOKS|PURSELL\s*PRINTING|HEIDELBERG\s*PRINT|MOO\.COM\s*BOOK)\b", re.I),
        category=TaxCategory.PHOTOBOOK_PRINTING,
        base_confidence=0.96,
        explanation="Photobook printing, short-run monograph bindery, or print-on-demand production (COGS).",
    ),
    MerchantRule(
        rule_id="PRINT_PRO_PHOTO_LAB",
        pattern=re.compile(r"\b(MILLERS\s*PRO|WHCC|WHITE\s*HOUSE\s*CUSTOM|BAY\s*PHOTO|RICHARD\s*PHOTO\s*LAB|INDIE\s*FILM\s*LAB|THE\s*FIND\s*LAB|CARMENCITA\s*FILM|DUGGAL\s*VISUAL|HAHNEMUHLE|ILFORD\s*PHOTO|KODAK\s*ALARIS|MOAB\s*PAPER)\b", re.I),
        category=TaxCategory.PHOTOBOOK_PRINTING,
        base_confidence=0.96,
        explanation="Professional darkroom lab processing, film scanning, or archival fine-art print stock (COGS).",
    ),

    # --- Software & Digital Workflow ---
    MerchantRule(
        rule_id="SW_EDITING_COLOR",
        pattern=re.compile(r"\b(ADOBE|CAPTURE\s*ONE|CAMERA\s*BITS|PHOTO\s*MECHANIC|DXO\s*LABS|IMAGEN\s*AI|AFTERSHOOT|RETROSPECT\s*COLOR|NEGATIVE\s*LAB\s*PRO)\b", re.I),
        category=TaxCategory.SOFTWARE_WORKFLOW,
        base_confidence=0.96,
        explanation="RAW photo editing, tethering, color grading, or DTP layout software (InDesign/Lightroom/Capture One).",
    ),
    MerchantRule(
        rule_id="SW_GALLERY_ARCHIVE",
        pattern=re.compile(r"\b(PIXIESET(?!\s*\*?\s*(?:PRINT\s*)?STORE\s*PAYOUT)|PIC-TIME(?!\s*\*?\s*PAYOUT)|PICTIME|SMUGMUG|ZENFOLIO|SHOOTPROOF|FRAME\.IO|BACKBLAZE|DROPBOX|GOOGLE\s*\*GSUITE|GOOGLE\s*\*WORKSPACE|HONEYBOOK(?!\s*\*?\s*(?:CLIENT\s*)?PAYOUT)|DUBSADO|17HATS|SQUARESPACE|CARGO\s*SITE|FORMAT\.COM)\b", re.I),
        category=TaxCategory.SOFTWARE_WORKFLOW,
        base_confidence=0.95,
        explanation="Client gallery delivery, cloud RAW backup, studio CRM, or portfolio web hosting subscription.",
    ),

    # --- Studio, Darkroom & Location Permits ---
    MerchantRule(
        rule_id="STUDIO_BOOKING_PERMITS",
        pattern=re.compile(r"\b(PEERSPACE|SPLACER|GIGGSTER|AVVAY|BROOKLYN\s*DARKROOM|GOWANUS\s*DARKROOM|LIGHTSPACE\s*STUDIO|MILK\s*STUDIOS|NPS\s*\*SPECIAL\s*USE|PARKS\s*FILMING\s*PERMIT|NYC\s*FILM\s*PERMIT|PUBLIC\s*STORAGE|CUBESMART)\b", re.I),
        category=TaxCategory.STUDIO_LOCATIONS,
        base_confidence=0.94,
        explanation="Hourly photo studio rental, community darkroom access, archival storage, or location shoot permit.",
    ),

    # --- Shoot Travel & Transport ---
    MerchantRule(
        rule_id="TRAVEL_RIDESHARE_TRANSIT",
        pattern=re.compile(r"\b(UBER\s*\*?TRIP|UBER\s*\*?BV|LYFT\s*\*?RIDE|CURB\s*TAXI|MTA\*NYCT|BART-CLIPPER|SPOTHERO|PARKWHIZ|LAZ\s*PARKING|ICON\s*PARKING|EZPASS)\b", re.I),
        category=TaxCategory.TRAVEL_TRANSPORT,
        base_confidence=0.91,
        explanation="Ground transportation, subway transit, tolls, or parking for on-location shoots.",
    ),
    MerchantRule(
        rule_id="TRAVEL_AIR_HOTEL_CAR",
        pattern=re.compile(r"\b(DELTA\s*AIR|UNITED\s*AIR|AMERICAN\s*AIR|JETBLUE|SOUTHWEST\s*AIR|ALASKA\s*AIR|MARRIOTT|HILTON|HYATT|ACE\s*HOTEL|AIRBNB|HERTZ|ENTERPRISE\s*RENT|AVIS\s*RENT|NATIONAL\s*CAR|AMTRAK)\b", re.I),
        category=TaxCategory.TRAVEL_TRANSPORT,
        base_confidence=0.93,
        explanation="Airfare, hotel lodging, rail, or rental car for out-of-town editorial assignments and book fairs.",
    ),

    # --- Shipping, Book Fulfillment & Packaging ---
    MerchantRule(
        rule_id="SHIP_CARRIERS_MAILERS",
        pattern=re.compile(r"\b(USPS\s*PO|USPS\.COM|PIRATESHIP|PIRATE\s*SHIP|STAMPS\.COM|FEDEX|UPS\s*STORE|UPS\s*BILLING|DHL\s*EXPRESS|ULINE|CLEARHARMONY\s*PACKAGING|GAYLORD\s*ARCHIVAL)\b", re.I),
        category=TaxCategory.SHIPPING_PACKAGING,
        base_confidence=0.94,
        explanation="Postage, courier shipping, rigid book mailers, or archival print sleeves.",
    ),

    # --- Props, Styling & Reference Photobooks ---
    MerchantRule(
        rule_id="PROPS_BOOKSTORES_PUBLISHING",
        pattern=re.compile(r"\b(PRINTED\s*MATTER(?!\s*FAIR)|DASHWOOD\s*BOOKS|ARCANA\s*BOOKS|APERTURE\s*FOUNDATION|STEIDL\s*VERLAG|TASCHEN|MACK\s*BOOKS|CHOSE\s*COMMUNE|STRAND\s*BOOK\s*STORE|POWELLS\s*BOOKS|SAVAGE\s*UNIVERSAL|ROSE\s*BRAND\s*BACKDROPS|MOOD\s*FABRICS)\b", re.I),
        category=TaxCategory.PROPS_REFERENCE_BOOKS,
        base_confidence=0.90,
        explanation="Photobook monograph research, seamless studio backdrops, or set styling materials.",
    ),

    # --- Client & Crew Meals (Explicit Shoot Catering Only) ---
    MerchantRule(
        rule_id="MEALS_SHOOT_CATERING",
        pattern=re.compile(r"\b(EZCATER|CATERING|CRAFT\s*SERVICES|PANERA\s*CATERING|SWEETGREEN\s*CATERING|DOORDASH\*CREW)\b", re.I),
        category=TaxCategory.CLIENT_CREW_MEALS,
        base_confidence=0.91,
        explanation="On-set shoot catering or craft services for crew and clients (50% deductible under IRS Schedule C Line 24b).",
        tax_flag=TaxFlag.MEALS_50_PERCENT,
    ),

    # --- Marketing, Book Fairs & Portfolio ---
    MerchantRule(
        rule_id="MKT_ADS_BOOKFAIRS",
        pattern=re.compile(r"\b(META\s*PLATFORMS\s*\*ADS|FACEBK\s*\*ADS|PINTEREST\s*\*ADS|GOOGLE\s*\*ADS|NY\s*ART\s*BOOK\s*FAIR|LA\s*ART\s*BOOK\s*FAIR|PARIS\s*PHOTO\s*BOOTH|POLYCOPIES|MOO\.COM(?!\s*BOOK)|FOUNDRY\s*PROMO)\b", re.I),
        category=TaxCategory.MARKETING_BOOK_FAIRS,
        base_confidence=0.94,
        explanation="Paid portfolio promotion, promo mailers, or art book fair exhibitor booth fee.",
    ),

    # --- Insurance, Legal, ISBN & Guilds ---
    MerchantRule(
        rule_id="INS_GUILDS_COPYRIGHT",
        pattern=re.compile(r"\b(HISCOX|ATHOS\s*INSURANCE|TCP\*ATHOS|THIMBLE\s*INS|PPA\s*MEMB|PROFESSIONAL\s*PHOTOG|ASMP\s*MEMB|NPPA|US\s*COPYRIGHT\s*OFFICE|COPYRIGHT\.GOV|BOWKER\s*ISBN|MYIDENTIFIERS\.COM)\b", re.I),
        category=TaxCategory.INSURANCE_LEGAL,
        base_confidence=0.96,
        explanation="Inland marine camera insurance, ISBN registration (Bowker), US Copyright filing, or photography guild dues.",
    ),
]


# ---------------------------------------------------------------------------
# Layer 3: Keyword & Contextual Heuristics (Moderate Confidence: 0.72 - 0.84)
# ---------------------------------------------------------------------------
KEYWORD_HEURISTICS: List[MerchantRule] = [
    MerchantRule(
        rule_id="KW_CAMERA_LENS",
        pattern=re.compile(r"\b(CAMERA|MEDIUM\s*FORMAT|ANALOG\s*FILM|DARKROOM|TRIPOD|STROBE|LIGHTMETER|35MM|120\s*FILM)\b", re.I),
        category=TaxCategory.CAMERA_EQUIPMENT,
        base_confidence=0.80,
        explanation="Matched photography equipment keyword heuristic.",
    ),
    MerchantRule(
        rule_id="KW_BOOKBINDING_PRINT",
        pattern=re.compile(r"\b(BOOKBINDING|BINDERY|LITHOGRAPHY|OFFSET\s*PRINT|FINE\s*ART\s*PRINT|ARCHIVAL\s*INK|GICLEE|COLOR\s*PROOF)\b", re.I),
        category=TaxCategory.PHOTOBOOK_PRINTING,
        base_confidence=0.82,
        explanation="Matched photobook printing / fine-art bindery keyword heuristic.",
    ),
    MerchantRule(
        rule_id="KW_STUDIO_PERMIT",
        pattern=re.compile(r"\b(PHOTO\s*STUDIO|CYCLORAMA|DAYLIGHT\s*LOFT|LOCATION\s*FEE|FILMING\s*PERMIT)\b", re.I),
        category=TaxCategory.STUDIO_LOCATIONS,
        base_confidence=0.81,
        explanation="Matched studio space or location permit keyword heuristic.",
    ),
    MerchantRule(
        rule_id="KW_SHIPPING",
        pattern=re.compile(r"\b(POSTAGE|FREIGHT|COURIER|MAILERS|SHIPPING\s*LABEL)\b", re.I),
        category=TaxCategory.SHIPPING_PACKAGING,
        base_confidence=0.78,
        explanation="Matched shipping and fulfillment keyword heuristic.",
    ),
    MerchantRule(
        rule_id="KW_HOTEL_AIR",
        pattern=re.compile(r"\b(AIRLINES|AIRWAYS|HOTEL|MOTEL|LODGING|PARKING\s*GARAGE|TOLLWAY)\b", re.I),
        category=TaxCategory.TRAVEL_TRANSPORT,
        base_confidence=0.79,
        explanation="Matched travel and transport keyword heuristic.",
    ),
]


# ---------------------------------------------------------------------------
# Layer 4: Ambiguity Traps (Force Needs Review when context is missing)
# ---------------------------------------------------------------------------
AMBIGUITY_TRAPS: List[AmbiguityTrap] = [
    AmbiguityTrap(
        trap_id="TRAP_AMAZON_MARKETPLACE",
        pattern=re.compile(r"\b(AMAZON|AMZN\s*MKTP|AMZN\.COM)\b", re.I),
        max_confidence=0.38,
        reason="Amazon Marketplace is a multi-category retailer: could be camera accessories (SD cards/gaffer tape), shipping mailers, reference books, or personal household items. Check order invoice.",
        suggested_categories=[
            TaxCategory.CAMERA_EQUIPMENT,
            TaxCategory.SHIPPING_PACKAGING,
            TaxCategory.PROPS_REFERENCE_BOOKS,
            TaxCategory.PERSONAL_NON_DEDUCTIBLE,
        ],
    ),
    AmbiguityTrap(
        trap_id="TRAP_BIG_BOX_RETAIL",
        pattern=re.compile(r"\b(TARGET|WALMART|COSTCO|BEST\s*BUY|APPLE\.COM/BILL|APPLE\s*STORE|IKEA)\b", re.I),
        max_confidence=0.40,
        reason="Mixed business/personal retailer — statement line does not specify whether purchase was studio hardware/props or personal goods.",
        suggested_categories=[
            TaxCategory.CAMERA_EQUIPMENT,
            TaxCategory.PROPS_REFERENCE_BOOKS,
            TaxCategory.SOFTWARE_WORKFLOW,
            TaxCategory.PERSONAL_NON_DEDUCTIBLE,
        ],
    ),
    AmbiguityTrap(
        trap_id="TRAP_P2P_PAYMENT",
        pattern=re.compile(r"\b(VENMO|PAYPAL\s*\*|ZELLE(?!\s*TO\s*SELF)|CASH\s*APP)\b", re.I),
        max_confidence=0.35,
        reason="Peer-to-peer transfer lacks a vendor invoice description — could be a second-shooter/stylist contractor, used lens purchase, or personal split.",
        suggested_categories=[
            TaxCategory.STUDIO_LOCATIONS,
            TaxCategory.PROPS_REFERENCE_BOOKS,
            TaxCategory.CAMERA_EQUIPMENT,
            TaxCategory.PERSONAL_NON_DEDUCTIBLE,
        ],
    ),
    AmbiguityTrap(
        trap_id="TRAP_LOCAL_CAFE_DINING",
        pattern=re.compile(r"\b(CAFE|COFFEE|ESPRESSO|ROASTERS|BAKERY|STARBUCKS|BLUE\s*BOTTLE|JOES\s*CAFE|BISTRO|TAVERN|BAR\s*&\s*GRILL|PIZZA|SUSHI|CHIPOTLE|SWEETGREEN(?!\s*CATERING)|TST\*|SQ\s*\*)\b", re.I),
        max_confidence=0.45,
        reason="Food/beverage charge lacks client or shoot crew context. Solo meals/coffee in your home city are non-deductible; client project meetings or on-set crew meals are 50% deductible.",
        suggested_categories=[
            TaxCategory.CLIENT_CREW_MEALS,
            TaxCategory.TRAVEL_TRANSPORT,
            TaxCategory.PERSONAL_NON_DEDUCTIBLE,
        ],
    ),
    AmbiguityTrap(
        trap_id="TRAP_ATM_CASH",
        pattern=re.compile(r"\b(ATM\s*WITHDRAWAL|CASH\s*WITHDRAWAL|NON-CHASE\s*ATM)\b", re.I),
        max_confidence=0.25,
        reason="Unreceipted ATM cash withdrawal — requires itemized paper receipts (e.g., on-set tips or prop market cash) to be deductible.",
        suggested_categories=[
            TaxCategory.PROPS_REFERENCE_BOOKS,
            TaxCategory.TRAVEL_TRANSPORT,
            TaxCategory.PERSONAL_NON_DEDUCTIBLE,
        ],
    ),
]


# Keywords indicating a transaction is a refund, return, credit, or deposit release
REFUND_INDICATOR_RE = re.compile(
    r"\b(REFUND|RETURN|CREDIT|REVERSAL|REBATE|DEPOSIT\s*RET|SEC\s*DEP\s*RELEASE|OVERPAYMENT|DISPUTE\s*CREDIT|DEFECT\s*CREDIT)\b",
    re.I,
)

# Keywords indicating a transaction is still pending / pre-authorization hold
PENDING_INDICATOR_RE = re.compile(
    r"\b(PENDING|PRE-?AUTH|AUTH\s*HOLD|PROVISIONAL)\b",
    re.I,
)

# Categories whose vendors are strictly expense-side (so a positive inflow from them is a refund/contra-expense, not revenue)
EXPENSE_ONLY_CATEGORIES = {
    TaxCategory.GEAR_RENTALS,
    TaxCategory.CAMERA_EQUIPMENT,
    TaxCategory.PHOTOBOOK_PRINTING,
    TaxCategory.SOFTWARE_WORKFLOW,
    TaxCategory.STUDIO_LOCATIONS,
    TaxCategory.TRAVEL_TRANSPORT,
    TaxCategory.SHIPPING_PACKAGING,
    TaxCategory.PROPS_REFERENCE_BOOKS,
    TaxCategory.CLIENT_CREW_MEALS,
    TaxCategory.MARKETING_BOOK_FAIRS,
    TaxCategory.INSURANCE_LEGAL,
    TaxCategory.BANK_MERCHANT_FEES,
}
