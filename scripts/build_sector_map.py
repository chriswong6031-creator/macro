"""Build data/breadth/ticker_sectors.parquet — a comprehensive ticker→GICS-sector map.

Sources (priority order):
  1. GICS direct: data/breadth/constituents.parquet (S&P 500, source='gics_sp500'),
                  data/midcap_breadth/constituents.parquet (S&P 400, source='gics_sp400'),
                  data/smallcap_breadth/constituents.parquet (S&P 600, source='gics_sp600').
     These carry exact GICS classification from the index provider.
  2. SIC text mapping: data/profile/profiles.parquet (.sic_description → sector via the
     _SIC_TEXT_MAP lookup table below, source='sic_mapped').
  3. Numeric SIC mapping: data/edgar/cik_sic.json (CIK→SIC) joined via
     data/edgar/fundamentals_panel.parquet (ticker→CIK), then SIC range→sector
     via _SIC_RANGE_MAP (source='sic_mapped').

Output: data/breadth/ticker_sectors.parquet with columns:
    ticker  str      stock symbol
    sector  str      one of the 11 GICS-style sector strings
    source  str      'gics_sp500' | 'gics_sp400' | 'gics_sp600' | 'sic_mapped'

Coverage target: ≥1,500 of the 2,589 sp1500_pit_membership tickers on first run
(limited by profiles.parquet coverage for historical/delisted tickers).  Coverage
grows on subsequent runs as the cik_sic.json drip cache fills via edgar_emergence.

GICS-style sector strings (matching constituents.parquet):
  Communication Services, Consumer Discretionary, Consumer Staples, Energy,
  Financials, Health Care, Industrials, Information Technology, Materials,
  Real Estate, Utilities

Program: Long-Hold Thesis Layer — LT-1c (sector map expansion).
Synapse: data/breadth/ticker_sectors.parquet (tier: display, horizon_role: context).
FIREWALL: display-only, horizon_role=context, scored_path_surfaces=[].
          MUST NOT feed board ordering / alert triage / entry-stack z-scores.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SIC text description → GICS sector mapping
# Covers all 306 unique sic_description values observed in data/profile/profiles.parquet
# plus the additional descriptions in data/edgar/cik_sic.json.
# Map is intentionally exhaustive for the observed universe; unmapped descriptions
# yield None (the caller drops those rows rather than guessing).
# ---------------------------------------------------------------------------
_SIC_TEXT_MAP: dict[str, str] = {
    # Energy
    "Crude Petroleum & Natural Gas": "Energy",
    "Oil & Gas Field Services, NEC": "Energy",
    "Oil & Gas Field Machinery & Equipment": "Energy",
    "Drilling Oil & Gas Wells": "Energy",
    "Petroleum Refining": "Energy",
    "Pipe Lines (No Natural Gas)": "Energy",
    "Oil Royalty Traders": "Energy",
    "Mineral Royalty Traders": "Energy",
    "Miscellaneous Products of  Petroleum & Coal": "Energy",
    "Wholesale-Petroleum & Petroleum Products (No Bulk Stations)": "Energy",
    "Bituminous Coal & Lignite Surface Mining": "Energy",
    "Coal Mining": "Energy",
    "Natural Gas Transmission": "Energy",
    "Natural Gas Transmisison & Distribution": "Energy",
    "Natural Gas Distribution": "Energy",
    "Cogeneration Services & Small Power Producers": "Energy",
    # Materials
    "Metal Mining": "Materials",
    "Mining & Quarrying of  Nonmetallic Minerals (No Fuels)": "Materials",
    "Gold and Silver Ores": "Materials",
    "Silver Ores": "Materials",
    "Agricultural Chemicals": "Materials",
    "Industrial Organic Chemicals": "Materials",
    "Industrial Inorganic Chemicals": "Materials",
    "Miscellaneous Chemical Products": "Materials",
    "Paints, Varnishes, Lacquers, Enamels & Allied Prods": "Materials",
    "Adhesives & Sealants": "Materials",
    "Plastic Material, Synth Resin/Rubber, Cellulos (No Glass)": "Materials",
    "Plastic Materials, Synth Resins & Nonvulcan Elastomers": "Materials",
    "Plastics Products, NEC": "Materials",
    "Plastics Foam Products": "Materials",
    "Plastics, Foil & Coated Paper Bags": "Materials",
    "Rubber & Plastics Footwear": "Materials",
    "Tires & Inner Tubes": "Materials",
    "Steel Works, Blast Furnaces & Rolling & Finishing Mills": "Materials",
    "Steel Works, Blast Furnaces & Rolling Mills (Coke Ovens)": "Materials",
    "Steel Pipe & Tubes": "Materials",
    "Primary Production of  Aluminum": "Materials",
    "Rolling Drawing & Extruding of  Nonferrous Metals": "Materials",
    "Nonferrous Foundries (Castings)": "Materials",
    "Drawing & Insulating of  Nonferrous Wire": "Materials",
    "Metal Cans": "Materials",
    "Metal Forgings & Stampings": "Materials",
    "Metal Shipping Barrels, Drums, Kegs & Pails": "Materials",
    "Miscellaneous Fabricated Metal Products": "Materials",
    "Fabricated Structural Metal Products": "Materials",
    "Fabricated Plate Work (Boiler Shops)": "Materials",
    "Metal Doors, Sash, Frames, Moldings & Trim": "Materials",
    "Metalworkg Machinery & Equipment": "Materials",
    "Abrasive, Asbestos & Misc Nonmetallic Mineral Prods": "Materials",
    "Chemicals & Allied Products": "Materials",
    "Paper Mills": "Materials",
    "Paperboard Containers & Boxes": "Materials",
    "Converted Paper & Paperboard Prods (No Contaners/Boxes)": "Materials",
    "Lumber & Wood Products (No Furniture)": "Materials",
    "Millwood, Veneer, Plywood, & Structural Wood Members": "Materials",
    "Sawmills & Planting Mills, General": "Materials",
    "Glass Containers": "Materials",
    "Glass Products, Made of  Purchased Glass": "Materials",
    "Cement, Hydraulic": "Materials",
    "Specialty Cleaning, Polishing and Sanitation Preparations": "Materials",
    "Soap, Detergents, Cleang Preparations, Perfumes, Cosmetics": "Materials",
    "Coating, Engraving & Allied Services": "Materials",
    # Industrials
    "General Bldg Contractors - Residential Bldgs": "Industrials",
    "General Bldg Contractors - Nonresidential Bldgs": "Industrials",
    "Heavy Construction Other Than Bldg Const - Contractors": "Industrials",
    "Construction - Special Trade Contractors": "Industrials",
    "Water, Sewer, Pipeline, Comm & Power Line Construction": "Industrials",
    "Operative Builders": "Industrials",
    "Land Subdividers & Developers (No Cemeteries)": "Industrials",
    "Construction, Mining & Materials Handling Machinery & Equip": "Industrials",
    "Construction Machinery & Equip": "Industrials",
    "Industrial Trucks, Tractors, Trailors & Stackers": "Industrials",
    "Farm Machinery & Equipment": "Industrials",
    "Lawn & Garden Tractors & Home Lawn & Gardens Equip": "Industrials",
    "Special Industry Machinery (No Metalworking Machinery)": "Industrials",
    "Special Industry Machinery, NEC": "Industrials",
    "Engines & Turbines": "Industrials",
    "General Industrial Machinery & Equipment": "Industrials",
    "General Industrial Machinery & Equipment, NEC": "Industrials",
    "Misc Industrial & Commercial Machinery & Equipment": "Industrials",
    "Machine Tools, Metal Cutting Types": "Industrials",
    "Pumps & Pumping Equipment": "Industrials",
    "Refrigeration & Service Industry Machinery": "Industrials",
    "Air-Cond & Warm Air Heatg Equip & Comm & Indl Refrig Equip": "Industrials",
    "Industrial & Commercial Fans & Blowers & Air Purifing Equip": "Industrials",
    "Heating Equip, Except Elec & Warm Air; & Plumbing Fixtures": "Industrials",
    "Electrical Work": "Industrials",
    "Electrical Industrial Apparatus": "Industrials",
    "Motors & Generators": "Industrials",
    "Switchgear & Switchboard Apparatus": "Industrials",
    "Miscellaneous Electrical Machinery, Equipment & Supplies": "Industrials",
    "Aircraft": "Industrials",
    "Aircraft & Parts": "Industrials",
    "Aircraft Engines & Engine Parts": "Industrials",
    "Aircraft Parts & Auxiliary Equipment, NEC": "Industrials",
    "Guided Missiles & Space Vehicles & Parts": "Industrials",
    "Search, Detection, Navigation, Guidance, Aeronautical Sys": "Industrials",
    "Ordnance & Accessories, (No Vehicles/Guided Missiles)": "Industrials",
    "Ship & Boat Building & Repairing": "Industrials",
    "Railroad Equipment": "Industrials",
    "Railroads, Line-Haul Operating": "Industrials",
    "Trucking & Courier Services (No Air)": "Industrials",
    "Trucking (No Local)": "Industrials",
    "Air Transportation, Scheduled": "Industrials",
    "Air Transportation, Nonscheduled": "Industrials",
    "Air Courier Services": "Industrials",
    "Water Transportation": "Industrials",
    "Deep Sea Foreign Transportation of  Freight": "Industrials",
    "Transportation Services": "Industrials",
    "Arrangement of  Transportation of  Freight & Cargo": "Industrials",
    "Miscellaneous Transportation Equipment": "Industrials",
    "Services-Engineering Services": "Industrials",
    "Services-Engineering, Accounting, Research, Management": "Industrials",
    "Services-Management Consulting Services": "Industrials",
    "Services-Management Services": "Industrials",
    "Services-Business Services, NEC": "Industrials",
    "Services-Miscellaneous Business Services": "Industrials",
    "Services-Employment Agencies": "Industrials",
    "Services-Help Supply Services": "Industrials",
    "Services-Detective, Guard & Armored Car Services": "Industrials",
    "Services-To Dwellings & Other Buildings": "Industrials",
    "Services-Equipment Rental & Leasing, NEC": "Industrials",
    "Services-Miscellaneous Equipment Rental & Leasing": "Industrials",
    "Services-Testing Laboratories": "Industrials",
    "Wholesale-Machinery, Equipment & Supplies": "Industrials",
    "Wholesale-Industrial Machinery & Equipment": "Industrials",
    "Wholesale-Hardware": "Industrials",
    "Wholesale-Hardware & Plumbing & Heating Equipment & Supplies": "Industrials",
    "Wholesale-Durable Goods": "Industrials",
    "Wholesale-Durable Goods, NEC": "Industrials",
    "Wholesale-Misc Durable Goods": "Industrials",
    "Wholesale-Metals Service Centers & of fices": "Industrials",
    "Wholesale-Lumber & Other Construction Materials": "Industrials",
    "Wholesale-Motor Vehicles & Motor Vehicle Parts & Supplies": "Industrials",
    "Wholesale-Motor Vehicle Supplies & New Parts": "Industrials",
    "Wholesale-Farm Product Raw Materials": "Industrials",
    "Hazardous Waste Management": "Industrials",
    "Refuse Systems": "Industrials",
    "Miscellaneous Manufacturing Industries": "Industrials",
    "Sporting & Athletic Goods, NEC": "Consumer Discretionary",  # Note: below
    # Consumer Discretionary
    "Motor Vehicles & Passenger Car Bodies": "Consumer Discretionary",
    "Motor Vehicle Parts & Accessories": "Consumer Discretionary",
    "Motorcycles, Bicycles & Parts": "Consumer Discretionary",
    "Household Furniture": "Consumer Discretionary",
    "Household Appliances": "Consumer Discretionary",
    "Household Audio & Video Equipment": "Consumer Discretionary",
    "Mobile Homes": "Consumer Discretionary",
    "Motor Homes": "Consumer Discretionary",
    "Carpets & Rugs": "Consumer Discretionary",
    "Hotels & Motels": "Consumer Discretionary",
    "Hotels, Rooming Houses, Camps & Other Lodging Places": "Consumer Discretionary",
    "Services-Amusement & Recreation Services": "Consumer Discretionary",
    "Services-Miscellaneous Amusement & Recreation": "Consumer Discretionary",
    "Services-Membership Sports & Recreation Clubs": "Consumer Discretionary",
    "Services-Racing, Including Track Operation": "Consumer Discretionary",
    "Services-Video Tape Rental": "Consumer Discretionary",
    "Services-Motion Picture & Video Tape Production": "Consumer Discretionary",
    "Retail-Department Stores": "Consumer Discretionary",
    "Retail-Eating  Places": "Consumer Discretionary",
    "Retail-Eating & Drinking Places": "Consumer Discretionary",
    "Retail-Family Clothing Stores": "Consumer Discretionary",
    "Retail-Women's Clothing Stores": "Consumer Discretionary",
    "Retail-Home Furniture, Furnishings & Equipment Stores": "Consumer Discretionary",
    "Retail-Furniture Stores": "Consumer Discretionary",
    "Retail-Jewelry Stores": "Consumer Discretionary",
    "Retail-Shoe Stores": "Consumer Discretionary",
    "Retail-Hobby, Toy & Game Shops": "Consumer Discretionary",
    "Retail-Radio, Tv & Consumer Electronics Stores": "Consumer Discretionary",
    "Retail-Auto & Home Supply Stores": "Consumer Discretionary",
    "Retail-Auto Dealers & Gasoline Stations": "Consumer Discretionary",
    "Retail-Retail Stores, NEC": "Consumer Discretionary",
    "Retail-Variety Stores": "Consumer Discretionary",
    "Retail-Miscellaneous Retail": "Consumer Discretionary",
    "Retail-Catalog & Mail-Order Houses": "Consumer Discretionary",
    "Retail-Computer & Computer Software Stores": "Consumer Discretionary",
    "Retail-Building Materials, Hardware, Garden Supply": "Consumer Discretionary",
    "Retail-Lumber & Other Building Materials Dealers": "Consumer Discretionary",
    "Services-Auto Rental & Leasing (No Drivers)": "Consumer Discretionary",
    "Services-Automotive Repair, Services & Parking": "Consumer Discretionary",
    "Footwear, (No Rubber)": "Consumer Discretionary",
    "Leather & Leather Products": "Consumer Discretionary",
    "Apparel & Other Finishd Prods of  Fabrics & Similar Matl": "Consumer Discretionary",
    "Men's & Boys' Furnishgs, Work Clothg, & Allied Garments": "Consumer Discretionary",
    "Broadwoven Fabric Mills, Man Made Fiber & Silk": "Consumer Discretionary",
    "Games, Toys & Children's Vehicles (No Dolls & Bicycles)": "Consumer Discretionary",
    "Ophthalmic Goods": "Consumer Discretionary",
    "Optical Instruments & Lenses": "Health Care",  # Reclassified below
    "Perfumes, Cosmetics & Other Toilet Preparations": "Consumer Staples",
    "Soap, Detergents, Cleang Preparations, Perfumes, Cosmetics": "Consumer Staples",
    # Consumer Staples
    "Food and Kindred Products": "Consumer Staples",
    "Grain Mill Products": "Consumer Staples",
    "Beverages": "Consumer Staples",
    "Malt Beverages": "Consumer Staples",
    "Bottled & Canned Soft Drinks & Carbonated Waters": "Consumer Staples",
    "Fats & Oils": "Consumer Staples",
    "Canned, Frozen & Preservd Fruit, Veg & Food Specialties": "Consumer Staples",
    "Canned, Fruits, Veg, Preserves, Jams & Jellies": "Consumer Staples",
    "Miscellaneous Food Preparations & Kindred Products": "Consumer Staples",
    "Sugar & Confectionery Products": "Consumer Staples",
    "Cookies & Crackers": "Consumer Staples",
    "Meat Packing Plants": "Consumer Staples",
    "Poultry Slaughtering and Processing": "Consumer Staples",
    "Cigarettes": "Consumer Staples",
    "Tobacco": "Consumer Staples",
    "Retail-Grocery Stores": "Consumer Staples",
    "Retail-Drug Stores and Proprietary Stores": "Consumer Staples",
    "Wholesale-Groceries & Related Products": "Consumer Staples",
    "Wholesale-Groceries, General Line": "Consumer Staples",
    "Wholesale-Drugs, Proprietaries & Druggists' Sundries": "Consumer Staples",
    "Agricultural Production-Crops": "Consumer Staples",
    "Agricultural Prod-Livestock & Animal Specialties": "Consumer Staples",
    "Agricultural Services": "Consumer Staples",
    # Health Care
    "Pharmaceutical Preparations": "Health Care",
    "Biological Products, (No Diagnostic Substances)": "Health Care",
    "In Vitro & In Vivo Diagnostic Substances": "Health Care",
    "Surgical & Medical Instruments & Apparatus": "Health Care",
    "Orthopedic, Prosthetic & Surgical Appliances & Supplies": "Health Care",
    "Dental Equipment & Supplies": "Health Care",
    "Electromedical & Electrotherapeutic Apparatus": "Health Care",
    "Services-General Medical & Surgical Hospitals, NEC": "Health Care",
    "Services-Hospitals": "Health Care",
    "Services-Health Services": "Health Care",
    "Services-Home Health Care Services": "Health Care",
    "Services-Nursing & Personal Care Facilities": "Health Care",
    "Services-Skilled Nursing Care Facilities": "Health Care",
    "Services-Medical Laboratories": "Health Care",
    "Services-Misc Health & Allied Services, NEC": "Health Care",
    "Services-Specialty Outpatient Facilities, NEC": "Health Care",
    "Services-Offices & Clinics of  Doctors of  Medicine": "Health Care",
    "Services-Child Day Care Services": "Health Care",
    "Services-Commercial Physical & Biological Research": "Health Care",
    "Hospital & Medical Service Plans": "Health Care",
    "Wholesale-Medical, Dental & Hospital Equipment & Supplies": "Health Care",
    "Optical Instruments & Lenses": "Health Care",
    # Information Technology
    "Electronic Computers": "Information Technology",
    "Computer Storage Devices": "Information Technology",
    "Computer & office Equipment": "Information Technology",
    "Computer Communications Equipment": "Information Technology",
    "Computer Peripheral Equipment, NEC": "Information Technology",
    "Printed Circuit Boards": "Information Technology",
    "Semiconductors & Related Devices": "Information Technology",
    "Electronic Components, NEC": "Information Technology",
    "Electronic Components & Accessories": "Information Technology",
    "Electronic Connectors": "Information Technology",
    "Radio & Tv Broadcasting & Communications Equipment": "Information Technology",
    "Telephone & Telegraph Apparatus": "Information Technology",
    "Communications Equipment, NEC": "Information Technology",
    "Industrial Instruments For Measurement, Display, and Control": "Information Technology",
    "Instruments For Meas & Testing of  Electricity & Elec Signals": "Information Technology",
    "Laboratory Analytical Instruments": "Information Technology",
    "Measuring & Controlling Devices, NEC": "Information Technology",
    "Totalizing Fluid Meters & Counting Devices": "Information Technology",
    "Auto Controls For Regulating Residential & Comml Environments": "Information Technology",
    "Services-Prepackaged Software": "Information Technology",
    "Services-Computer Programming Services": "Information Technology",
    "Services-Computer Programming, Data Processing, Etc.": "Information Technology",
    "Services-Computer Processing & Data Preparation": "Information Technology",
    "Services-Computer Integrated Systems Design": "Information Technology",
    "Wholesale-Computers & Peripheral Equipment & Software": "Information Technology",
    "Wholesale-Electronic Parts & Equipment, NEC": "Information Technology",
    "Wholesale-Electrical Apparatus & Equipment, Wiring Supplies ": "Information Technology",
    "Calculating & Accounting Machines (No Electronic Computers)": "Information Technology",
    "Office Machines, NEC": "Information Technology",
    # Communication Services
    "Telephone Communications (No Radiotelephone)": "Communication Services",
    "Radiotelephone Communications": "Communication Services",
    "Telegraph & Other Message Communications": "Communication Services",
    "Communications Services, NEC": "Communication Services",
    "Radio Broadcasting Stations": "Communication Services",
    "Television Broadcasting Stations": "Communication Services",
    "Cable & Other Pay Television Services": "Communication Services",
    "Books: Publishing or  Publishing & Printing": "Communication Services",
    "Blankbooks, Looseleaf Binders & Bookbindg & Relatd Work": "Communication Services",
    "Newspapers: Publishing or  Publishing & Printing": "Communication Services",
    "Services-Advertising Agencies": "Communication Services",
    "Services-Educational Services": "Communication Services",
    "Services-Personal Services": "Communication Services",
    # Utilities
    "Electric Services": "Utilities",
    "Electric & Other Services Combined": "Utilities",
    "Gas & Other Services Combined": "Utilities",
    "Electric, Gas & Sanitary Services": "Utilities",
    "Water Supply": "Utilities",
    "Natural Gas Transmission": "Utilities",
    "Natural Gas Transmisison & Distribution": "Utilities",
    "Natural Gas Distribution": "Utilities",
    "Cogeneration Services & Small Power Producers": "Utilities",
    # Financials
    "National Commercial Banks": "Financials",
    "State Commercial Banks": "Financials",
    "Savings Institution, Federally Chartered": "Financials",
    "Savings Institutions, Not Federally Chartered": "Financials",
    "Personal Credit Institutions": "Financials",
    "Short-Term Business Credit Institutions": "Financials",
    "Functions Related To Depository Banking, NEC": "Financials",
    "Security Brokers, Dealers & Flotation Companies": "Financials",
    "Security & Commodity Brokers, Dealers, Exchanges & Services": "Financials",
    "Investment Advice": "Financials",
    "Investors, NEC": "Financials",
    "Finance Services": "Financials",
    "Life Insurance": "Financials",
    "Fire, Marine & Casualty Insurance": "Financials",
    "Accident & Health Insurance": "Financials",
    "Surety Insurance": "Financials",
    "Title Insurance": "Financials",
    "Insurance Carriers, NEC": "Financials",
    "Insurance Agents, Brokers & Service": "Financials",
    "Hospital & Medical Service Plans": "Financials",
    "Services-Consumer Credit Reporting, Collection Agencies": "Financials",
    # Real Estate
    "Real Estate": "Real Estate",
    "Real Estate Investment Trusts": "Real Estate",
    "Real Estate Operators (No Developers) & Lessors": "Real Estate",
    "Real Estate Agents & Managers (For Others)": "Real Estate",
    "Land Subdividers & Developers (No Cemeteries)": "Real Estate",
    "Patent Owners & Lessors": "Real Estate",
}

# Reclassifications: some SIC entries above appear in multiple categories;
# keep the last assignment for duplicates in the dict literal (Python uses last).

# ---------------------------------------------------------------------------
# SIC numeric code range → GICS sector
# Standard SIC divisions (4-digit numeric codes).
# Used when we have the numeric SIC from cik_sic.json but no text description.
# Ranges reference the SEC SIC Manual divisions.
# ---------------------------------------------------------------------------
_SIC_RANGE_MAP: list[tuple[int, int, str]] = [
    # Agriculture, Forestry, Fishing
    (100, 999, "Consumer Staples"),
    # Mining: oil & gas (1311) + services (1380-1389)
    (1000, 1099, "Materials"),    # metal mining
    (1200, 1299, "Materials"),    # coal mining
    (1300, 1399, "Energy"),       # oil & gas extraction
    (1400, 1499, "Materials"),    # nonmetallic minerals
    # Construction
    (1500, 1799, "Industrials"),
    # Manufacturing: food & beverage (2000-2111)
    (2000, 2111, "Consumer Staples"),
    (2112, 2199, "Consumer Staples"),  # tobacco
    (2200, 2399, "Consumer Discretionary"),  # textiles, apparel
    (2400, 2499, "Materials"),     # lumber
    (2500, 2599, "Consumer Discretionary"),  # furniture
    (2600, 2699, "Materials"),     # paper
    (2700, 2799, "Communication Services"),  # printing/publishing
    (2800, 2899, "Materials"),     # chemicals
    (2830, 2836, "Health Care"),   # pharma — overrides 2800-2899 range below
    (2900, 2999, "Energy"),        # petroleum products
    (3000, 3099, "Materials"),     # rubber
    (3100, 3199, "Consumer Discretionary"),  # leather
    (3200, 3299, "Materials"),     # stone/glass
    (3300, 3399, "Materials"),     # primary metals
    (3400, 3499, "Materials"),     # fabricated metals
    (3500, 3599, "Industrials"),   # machinery
    (3600, 3699, "Information Technology"),  # electrical/electronics
    (3670, 3679, "Information Technology"),  # semiconductors/components — same tier
    (3700, 3799, "Consumer Discretionary"),  # transportation equipment
    (3710, 3716, "Consumer Discretionary"),  # motor vehicles
    (3720, 3729, "Industrials"),   # aircraft — override autos
    (3730, 3739, "Industrials"),   # ship building
    (3740, 3749, "Industrials"),   # railroad equipment
    (3760, 3769, "Industrials"),   # guided missiles
    (3800, 3899, "Information Technology"),  # instruments
    (3841, 3851, "Health Care"),   # medical instruments — override 3800 range
    (3900, 3999, "Consumer Discretionary"),  # misc manufacturing
    # Transportation
    (4000, 4099, "Industrials"),   # railroads
    (4100, 4299, "Industrials"),   # passenger / freight transport
    (4400, 4499, "Industrials"),   # water transport
    (4500, 4599, "Industrials"),   # air transport
    (4600, 4699, "Energy"),        # pipelines
    (4700, 4799, "Industrials"),   # transport services
    # Communications
    (4800, 4813, "Communication Services"),
    (4814, 4899, "Communication Services"),
    # Utilities
    (4900, 4999, "Utilities"),
    # Wholesale
    (5000, 5199, "Industrials"),
    # Retail
    (5200, 5999, "Consumer Discretionary"),
    (5900, 5949, "Consumer Discretionary"),
    (5912, 5912, "Consumer Staples"),  # drug stores
    (5400, 5499, "Consumer Staples"),  # food stores
    # Finance
    (6000, 6099, "Financials"),    # banks
    (6100, 6199, "Financials"),    # credit
    (6200, 6299, "Financials"),    # brokers
    (6300, 6399, "Financials"),    # insurance
    (6400, 6411, "Financials"),    # insurance agents
    (6500, 6552, "Real Estate"),   # real estate
    (6700, 6799, "Financials"),    # holding companies
    (6798, 6798, "Real Estate"),   # REITs — override holding companies
    # Services
    (7000, 7099, "Consumer Discretionary"),  # hotels
    (7200, 7299, "Consumer Discretionary"),  # personal services
    (7300, 7399, "Industrials"),   # business services
    (7370, 7379, "Information Technology"),  # computer services — override business
    (7380, 7389, "Industrials"),   # misc business services
    (7500, 7599, "Consumer Discretionary"),  # auto repair, rental
    (7600, 7699, "Consumer Discretionary"),  # misc repair
    (7800, 7899, "Communication Services"),  # entertainment
    (7900, 7999, "Consumer Discretionary"),  # amusement
    (8000, 8099, "Health Care"),   # health services
    (8100, 8199, "Industrials"),   # legal services (treat as professional services)
    (8200, 8299, "Communication Services"),  # educational services
    (8700, 8799, "Industrials"),   # engineering/management
    (8731, 8734, "Health Care"),   # commercial research — often biotech context
    (9100, 9999, "Industrials"),   # public administration/government
]


def _sic_range_to_sector(sic: int) -> str | None:
    """Map a numeric SIC code to a GICS sector string.

    The ranges in _SIC_RANGE_MAP are checked in order; later (more specific)
    entries win over earlier (broader) ones by reversing the list so the last
    match applies.  This handles override cases like 2830-2836 (pharma) inside
    the broader 2800-2899 (chemicals) bracket.
    """
    # Walk in reverse to let later (more specific) entries override earlier ones
    for lo, hi, sector in reversed(_SIC_RANGE_MAP):
        if lo <= sic <= hi:
            return sector
    return None


def _load_gics() -> dict[str, tuple[str, str]]:
    """{ticker: (sector, source)} from all three S&P index constituent files."""
    from lib import config  # noqa: PLC0415
    data_dir = config.data_dir()
    out: dict[str, tuple[str, str]] = {}
    for path, src in [
        (data_dir / "breadth" / "constituents.parquet", "gics_sp500"),
        (data_dir / "midcap_breadth" / "constituents.parquet", "gics_sp400"),
        (data_dir / "smallcap_breadth" / "constituents.parquet", "gics_sp600"),
    ]:
        if not path.exists():
            log.warning("GICS file not found: %s", path)
            continue
        try:
            df = pd.read_parquet(path)
            for t, row in df.iterrows():
                sec = row.get("sector")
                if pd.notna(sec) and str(sec).strip():
                    out.setdefault(str(t), (str(sec), src))
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load %s: %s", path, exc)
    log.info("GICS: %d tickers from constituent files", len(out))
    return out


def _load_sic_text() -> dict[str, str | None]:
    """{ticker: sector | None} from profiles.parquet via _SIC_TEXT_MAP."""
    from lib import config  # noqa: PLC0415
    path = config.data_dir() / "profile" / "profiles.parquet"
    if not path.exists():
        log.warning("profiles.parquet not found: %s", path)
        return {}
    try:
        df = pd.read_parquet(path, columns=["sic_description"])
    except Exception as exc:  # noqa: BLE001
        log.warning("profiles.parquet load failed: %s", exc)
        return {}
    out: dict[str, str | None] = {}
    for t, row in df.iterrows():
        desc = row.get("sic_description")
        if pd.notna(desc) and desc:
            sector = _SIC_TEXT_MAP.get(str(desc))
            out[str(t)] = sector  # None if unmapped
    log.info("SIC text: %d tickers with a description, %d mapped to sector",
             len(out), sum(1 for s in out.values() if s is not None))
    return out


def _load_sic_numeric() -> dict[str, str | None]:
    """{ticker: sector | None} from cik_sic.json via panel CIK + _SIC_RANGE_MAP."""
    from lib import config  # noqa: PLC0415
    cik_sic_path = config.data_dir() / "edgar" / "cik_sic.json"
    panel_path = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not cik_sic_path.exists():
        log.warning("cik_sic.json not found: %s", cik_sic_path)
        return {}
    try:
        cik_sic = json.loads(cik_sic_path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("cik_sic.json load failed: %s", exc)
        return {}
    if not panel_path.exists():
        log.warning("fundamentals_panel.parquet not found; skipping SIC numeric")
        return {}
    try:
        panel = pd.read_parquet(panel_path, columns=["ticker", "cik"])
    except Exception as exc:  # noqa: BLE001
        log.warning("fundamentals_panel load failed: %s", exc)
        return {}
    # Build ticker→CIK (zero-padded 10-digit string)
    ticker_cik: dict[str, str] = {}
    for _, row in panel[["ticker", "cik"]].drop_duplicates().iterrows():
        try:
            ticker_cik[str(row["ticker"])] = str(int(row["cik"])).zfill(10)
        except (ValueError, TypeError):
            pass
    out: dict[str, str | None] = {}
    for t, cik_str in ticker_cik.items():
        entry = cik_sic.get(cik_str)
        if not entry:
            continue
        sic_raw = entry.get("sic")
        sic_desc = entry.get("sic_desc")
        # Try text map first (more precise than numeric range)
        if sic_desc:
            sector = _SIC_TEXT_MAP.get(str(sic_desc))
            if sector:
                out[t] = sector
                continue
        # Fall back to numeric range
        if sic_raw:
            try:
                sic_int = int(str(sic_raw).strip())
                out[t] = _sic_range_to_sector(sic_int)
            except (ValueError, TypeError):
                pass
    mapped = sum(1 for s in out.values() if s is not None)
    log.info("SIC numeric: %d tickers in cik_sic→panel chain, %d mapped to sector",
             len(out), mapped)
    return out


def build(force: bool = False) -> pd.DataFrame:
    """Build and write data/breadth/ticker_sectors.parquet.

    Priority: GICS > SIC text > SIC numeric.  Tickers already in GICS are never
    overwritten by SIC-derived mappings.

    Returns the DataFrame written.
    """
    from lib import config  # noqa: PLC0415
    out_path = config.data_dir() / "breadth" / "ticker_sectors.parquet"
    meta_path = config.data_dir() / "breadth" / "ticker_sectors_meta.json"

    # Same-day skip (idempotent on daily re-runs), keyed off the committed
    # sidecar's build date — never source-vs-output mtime ordering. On CI
    # runners a checkout rewrites every file with mtime = checkout time, so
    # the old make-style comparison read "sources not newer" and silently
    # skipped rebuilds against newer committed sources (the polygon-universe
    # frozen-cache class, #2690). Missing/unreadable stamp ⇒ rebuild.
    if not force and out_path.exists():
        try:
            built = json.loads(meta_path.read_text()).get("built_asof")
            if built == date.today().isoformat():
                existing = pd.read_parquet(out_path)
                log.info("ticker_sectors.parquet already built today (%d tickers)",
                         len(existing))
                return existing
        except Exception:  # noqa: BLE001
            pass

    # --- Load sources ---
    gics = _load_gics()
    sic_text = _load_sic_text()
    sic_num = _load_sic_numeric()

    # --- Merge: GICS wins, then SIC text, then SIC numeric ---
    result: dict[str, tuple[str, str]] = dict(gics)  # {ticker: (sector, source)}

    # SIC text fills gaps
    for t, sector in sic_text.items():
        if sector and t not in result:
            result[t] = (sector, "sic_mapped")

    # SIC numeric fills remaining gaps
    for t, sector in sic_num.items():
        if sector and t not in result:
            result[t] = (sector, "sic_mapped")

    # Build DataFrame
    rows = [{"ticker": t, "sector": sec, "source": src} for t, (sec, src) in result.items()]
    df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)

    # --- Coverage report ---
    from lib import config as _config  # noqa: PLC0415
    sp1500_path = _config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if sp1500_path.exists():
        try:
            sp1500 = pd.read_parquet(sp1500_path)
            sp1500_tickers = set(sp1500["ticker"].unique())
            mapped_sp1500 = len(set(df["ticker"]) & sp1500_tickers)
            log.info(
                "ticker_sectors: %d total tickers, %d/%d sp1500_pit_membership mapped (%.1f%%)",
                len(df), mapped_sp1500, len(sp1500_tickers),
                100.0 * mapped_sp1500 / len(sp1500_tickers) if sp1500_tickers else 0,
            )
            log.info("source breakdown: %s",
                     df.groupby("source").size().to_dict())
            log.info("sector breakdown: %s",
                     df.groupby("sector").size().to_dict())
        except Exception as exc:  # noqa: BLE001
            log.warning("coverage check failed: %s", exc)
    else:
        log.info("ticker_sectors: %d total tickers", len(df))

    # --- Write ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    # Committed build stamp — the content-truth freshness signal for the
    # same-day skip above and for downstream as_of displays (#2690 class).
    meta_path.write_text(json.dumps(
        {"built_asof": date.today().isoformat(), "n_tickers": int(len(df))}))
    log.info("Written: %s (%d rows)", out_path, len(df))
    return df


def main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    parser = argparse.ArgumentParser(
        description="Build data/breadth/ticker_sectors.parquet "
                    "(GICS + SIC-derived sector map)."
    )
    parser.add_argument("--force", action="store_true",
                        help="Rebuild even if the output is up to date.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        df = build(force=args.force)
        print(f"ticker_sectors: {len(df)} tickers")
        print(df.groupby("source").size().to_string())
        print()
        print(df.groupby("sector").size().to_string())
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("build_sector_map failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
