"""
UK Chart of Accounts Templates

Three templates covering the most common UK business structures:
1. Limited Company (FRS 102 Section 1A) — most companies
2. Sole Trader — freelancers, self-employed
3. Micro-Entity (FRS 105) — very small companies (turnover < £632k)

Each account includes:
- code: Numeric code following UK convention (1000s = assets, 2000s = liabilities, etc.)
- name: UK terminology (Trade Debtors, not Accounts Receivable)
- type: asset / liability / equity / revenue / expense
- subtype: More specific classification for reporting
- balance: Normal balance direction (debit / credit)
- tax: Tax treatment (deductible / non_deductible / capitalized / n/a)
- description: What this account is for (helps AI classification)
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models import Account


# Account dict keys: code, name, type, subtype, balance, tax, description
LIMITED_COMPANY_UK: List[Dict] = [
    # ──────────────────────────────────────────
    # ASSETS (1000-1999)
    # ──────────────────────────────────────────

    # Current Assets (1000-1299)
    {"code": "1000", "name": "Cash at Bank", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Main business bank account. All incoming payments and outgoing payments flow through here."},

    {"code": "1010", "name": "Petty Cash", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Small cash float for minor expenses like milk, postage stamps, parking."},

    {"code": "1020", "name": "Savings Account", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Business savings or deposit account for reserves."},

    {"code": "1100", "name": "Trade Debtors", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Money owed TO you by customers for goods/services you've invoiced but not yet been paid for. Also called Accounts Receivable."},

    {"code": "1101", "name": "Other Debtors", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Money owed to you that isn't from normal trading — e.g., deposits, loans to employees, HMRC refunds."},

    {"code": "1200", "name": "Prepayments", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Amounts you've paid in advance for services not yet received — e.g., annual insurance premium paid upfront, software licences paid yearly."},

    {"code": "1300", "name": "Stock (Inventory)", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Goods held for resale. Cost of stock on hand at period end."},

    {"code": "1310", "name": "Work in Progress", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a",
     "description": "Partially completed work — e.g., a construction job or long-term project started but not invoiced yet."},

    # Fixed Assets (1400-1599)
    {"code": "1400", "name": "Plant & Equipment", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized",
     "description": "Machinery, tools, and equipment with a useful life > 1 year. Capital allowances claimed instead of expensing."},

    {"code": "1410", "name": "Computer Equipment", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized",
     "description": "Laptops, desktops, servers, monitors, printers. Items over your capitalisation threshold (typically £500+)."},

    {"code": "1420", "name": "Furniture & Fixtures", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized",
     "description": "Office desks, chairs, shelving, lighting. Items with lasting value."},

    {"code": "1430", "name": "Motor Vehicles", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized",
     "description": "Company-owned cars, vans, lorries. Subject to special capital allowance rules (CO2-based)."},

    {"code": "1440", "name": "Leasehold Improvements", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized",
     "description": "Improvements to a rented property — e.g., partitioning, rewiring, decoration of leased office."},

    {"code": "1500", "name": "Accumulated Depreciation — Equipment", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a",
     "description": "Total depreciation charged on plant & equipment to date. Reduces the net book value."},

    {"code": "1510", "name": "Accumulated Depreciation — Computers", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a",
     "description": "Total depreciation charged on computer equipment to date."},

    {"code": "1520", "name": "Accumulated Depreciation — Furniture", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a",
     "description": "Total depreciation charged on furniture & fixtures to date."},

    {"code": "1530", "name": "Accumulated Depreciation — Motor Vehicles", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a",
     "description": "Total depreciation charged on motor vehicles to date."},

    {"code": "1540", "name": "Accumulated Depreciation — Leasehold", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a",
     "description": "Total depreciation (amortisation) charged on leasehold improvements."},

    # ──────────────────────────────────────────
    # LIABILITIES (2000-2999)
    # ──────────────────────────────────────────

    # Current Liabilities (2000-2699)
    {"code": "2000", "name": "Trade Creditors", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Money you owe TO suppliers for goods/services received but not yet paid for. Also called Accounts Payable."},

    {"code": "2010", "name": "Other Creditors", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Amounts owed that aren't normal trade payables — e.g., employee expense claims, credit card balances."},

    {"code": "2100", "name": "VAT Control Account", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Net VAT position. Debit balance = HMRC owes you (reclaim). Credit balance = you owe HMRC."},

    {"code": "2110", "name": "VAT Input (Recoverable)", "type": "liability", "subtype": "current_liability",
     "balance": "debit", "tax": "n/a",
     "description": "VAT you've been charged on purchases and can reclaim from HMRC. Cleared to VAT Control on each return."},

    {"code": "2120", "name": "VAT Output (Payable)", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "VAT you've charged customers and must pay to HMRC. Cleared to VAT Control on each return."},

    {"code": "2200", "name": "PAYE & NI Liability", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Income tax and National Insurance withheld from employees' wages, plus employer's NI. Payable to HMRC by 22nd of following month."},

    {"code": "2210", "name": "Pension Liability", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Auto-enrolment pension contributions deducted from wages plus employer contributions. Payable to your pension provider."},

    {"code": "2300", "name": "Corporation Tax Liability", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Estimated corporation tax owed on this year's profits. Currently 25% for profits over £250k, 19% for profits under £50k (marginal relief between)."},

    {"code": "2400", "name": "Accruals", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Expenses you've incurred but haven't been invoiced for yet — e.g., unpaid electricity for the current month, accountant's year-end fee."},

    {"code": "2410", "name": "Deferred Income", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Money received from customers for goods/services not yet delivered — e.g., annual subscription paid upfront, deposit for future work."},

    {"code": "2500", "name": "Director's Loan Account", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Running balance between director and company. Credit = director has lent money to the company. Debit = director owes the company (Section 455 tax implications)."},

    {"code": "2510", "name": "Credit Card", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Business credit card balance. Each purchase is a credit card expense; payments reduce this balance."},

    # Long-Term Liabilities (2600-2999)
    {"code": "2600", "name": "Bank Loan", "type": "liability", "subtype": "long_term_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Long-term bank borrowing. Interest is deductible; capital repayments are not a P&L item."},

    {"code": "2610", "name": "Hire Purchase / Finance Lease", "type": "liability", "subtype": "long_term_liability",
     "balance": "credit", "tax": "n/a",
     "description": "Outstanding balance on assets bought on HP or finance lease. The asset goes on the balance sheet; the liability reduces as you make payments."},

    {"code": "2700", "name": "Bounce Back Loan / CBILS", "type": "liability", "subtype": "long_term_liability",
     "balance": "credit", "tax": "n/a",
     "description": "COVID-era government-backed loans. Track separately for reporting. Interest is deductible."},

    # ──────────────────────────────────────────
    # EQUITY (3000-3999)
    # ──────────────────────────────────────────
    {"code": "3000", "name": "Share Capital", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a",
     "description": "Nominal value of shares issued. For most small companies this is £1 (1 ordinary share of £1)."},

    {"code": "3010", "name": "Share Premium", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a",
     "description": "Amount paid for shares above their nominal value — e.g., if a £1 share is sold for £10, £9 goes here."},

    {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a",
     "description": "Accumulated profits not yet distributed as dividends. This is the company's 'savings'. Year-end profit/loss closes to this account."},

    {"code": "3200", "name": "Dividends Paid", "type": "equity", "subtype": "equity",
     "balance": "debit", "tax": "n/a",
     "description": "Dividends declared and paid to shareholders. Reduces retained earnings. NOT a tax-deductible expense."},

    # ──────────────────────────────────────────
    # REVENUE (4000-4999)
    # ──────────────────────────────────────────
    {"code": "4000", "name": "Sales Revenue", "type": "revenue", "subtype": "operating_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Main trading income. Revenue from your core business activity — invoiced sales, project fees, product sales."},

    {"code": "4010", "name": "Sales — Services", "type": "revenue", "subtype": "operating_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Revenue from services rendered (consultancy, professional fees, project work)."},

    {"code": "4020", "name": "Sales — Products", "type": "revenue", "subtype": "operating_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Revenue from physical goods sold."},

    {"code": "4100", "name": "Other Income", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Income outside your normal trading activity — e.g., insurance payouts, one-off receipts, miscellaneous income."},

    {"code": "4200", "name": "Interest Received", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Bank interest earned on savings or deposit accounts. Taxable as part of trading profits (for companies)."},

    {"code": "4300", "name": "Rental Income", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Income from subletting property or renting out assets."},

    {"code": "4400", "name": "Commission Received", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Commission or referral fees received from third parties."},

    {"code": "4500", "name": "Grants Received", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a",
     "description": "Government or local authority grants. May have specific recognition rules under FRS 102."},

    # ──────────────────────────────────────────
    # COST OF SALES (5000-5999)
    # ──────────────────────────────────────────
    {"code": "5000", "name": "Cost of Sales", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible",
     "description": "Direct costs of goods sold — materials, components, goods purchased for resale. Reduces gross profit."},

    {"code": "5010", "name": "Direct Labour", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible",
     "description": "Wages for staff directly involved in producing goods/delivering services. Subcontractor costs."},

    {"code": "5020", "name": "Subcontractor Costs", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible",
     "description": "Payments to subcontractors for work on client projects. CIS deductions apply in construction."},

    {"code": "5100", "name": "Carriage / Freight", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible",
     "description": "Shipping and delivery costs for goods sold. Courier fees, Royal Mail, pallet deliveries."},

    # ──────────────────────────────────────────
    # OVERHEADS / OPERATING EXPENSES (6000-7999)
    # ──────────────────────────────────────────

    # Staff Costs (6000-6099)
    {"code": "6000", "name": "Wages & Salaries", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Gross wages and salaries for employees (before PAYE/NI deductions). Fully deductible."},

    {"code": "6010", "name": "Employer's NI Contributions", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Employer's National Insurance — currently 13.8% on earnings above the secondary threshold. Fully deductible."},

    {"code": "6020", "name": "Pension Contributions (Employer)", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Employer pension contributions under auto-enrolment. Minimum 3% of qualifying earnings. Fully deductible."},

    {"code": "6030", "name": "Staff Training", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Training courses, CPD, professional development for employees. Deductible if wholly and exclusively for the business."},

    {"code": "6040", "name": "Recruitment Costs", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Agency fees, job adverts, interview expenses. Deductible."},

    {"code": "6050", "name": "Staff Welfare", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Tea, coffee, fruit for the office, staff Christmas party (up to £150/head is tax-free). Trivial benefits under £50."},

    {"code": "6060", "name": "Director's Remuneration", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Salary paid to directors. Disclosed separately in accounts. Fully deductible. Often set at NI threshold for tax efficiency."},

    # Premises Costs (6100-6199)
    {"code": "6100", "name": "Rent", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Office, warehouse, or shop rent. Deductible. If working from home, only the business proportion."},

    {"code": "6110", "name": "Business Rates", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Non-domestic rates charged by the local authority. Deductible. Small business rates relief may apply."},

    {"code": "6120", "name": "Light & Heat", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Electricity, gas, water for business premises. VAT on energy is 5% (domestic) or 20% (business)."},

    {"code": "6130", "name": "Cleaning", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Office cleaning, waste disposal, hygiene supplies."},

    {"code": "6140", "name": "Property Insurance", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Buildings and contents insurance for business premises."},

    # General & Admin (6200-6499)
    {"code": "6200", "name": "General Insurance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Business insurance — professional indemnity, public liability, employer's liability, cyber. All deductible."},

    {"code": "6300", "name": "Repairs & Maintenance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Repairs to equipment, premises, vehicles. Revenue repairs are deductible; improvements are capital."},

    {"code": "6400", "name": "Motor Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Fuel, MOT, road tax, servicing, breakdown cover for company vehicles. Personal use proportion is disallowed."},

    {"code": "6410", "name": "Mileage Claims", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "HMRC approved mileage rates for business use of personal vehicles: 45p/mile first 10,000 then 25p/mile (cars)."},

    {"code": "6500", "name": "Travel & Subsistence", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Travel to client sites, hotels for business trips, meals while travelling. Must be wholly business purpose."},

    {"code": "6600", "name": "Telephone & Internet", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Business phone line, mobile contracts, broadband. Personal use proportion should be disallowed."},

    {"code": "6700", "name": "Postage & Stationery", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Stamps, couriers, paper, ink, envelopes, office stationery."},

    {"code": "6710", "name": "Printing & Copying", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Printing, photocopying, binding. Includes outsourced print jobs."},

    {"code": "6800", "name": "Advertising & Marketing", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Google Ads, Facebook Ads, flyers, website costs, PR, exhibitions, trade shows."},

    {"code": "6810", "name": "Website & Hosting", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Domain registration, web hosting, SSL certificates, website maintenance."},

    {"code": "6900", "name": "Accountancy Fees", "type": "expense", "subtype": "professional_fees",
     "balance": "debit", "tax": "deductible",
     "description": "Fees for accountant, bookkeeper, tax agent, Companies House filing. Fully deductible."},

    {"code": "6910", "name": "Legal Fees", "type": "expense", "subtype": "professional_fees",
     "balance": "debit", "tax": "deductible",
     "description": "Solicitor fees for contracts, disputes, property. Revenue legal costs are deductible; capital legal costs (e.g., buying property) are not."},

    {"code": "6920", "name": "Consultancy Fees", "type": "expense", "subtype": "professional_fees",
     "balance": "debit", "tax": "deductible",
     "description": "IT consultants, business advisors, HR consultants, management consultants."},

    # Finance Costs (7000-7099)
    {"code": "7000", "name": "Bank Charges", "type": "expense", "subtype": "finance_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Monthly bank fees, transaction charges, card processing fees (Stripe, SumUp, etc.). Deductible."},

    {"code": "7010", "name": "Interest Paid", "type": "expense", "subtype": "finance_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Interest on loans, overdrafts, HP agreements. Deductible (subject to corporate interest restriction for large companies)."},

    {"code": "7020", "name": "Foreign Exchange Losses", "type": "expense", "subtype": "finance_costs",
     "balance": "debit", "tax": "deductible",
     "description": "Losses from currency conversion when paying/receiving foreign invoices."},

    # Software & Technology (7100-7199)
    {"code": "7100", "name": "Software Subscriptions", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "SaaS subscriptions — Xero, Microsoft 365, Slack, Zoom, etc. Monthly/annual fees are revenue expenditure."},

    {"code": "7110", "name": "IT Support & Maintenance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Managed IT services, antivirus, backup services, tech support contracts."},

    # Depreciation (7200)
    {"code": "7200", "name": "Depreciation", "type": "expense", "subtype": "depreciation",
     "balance": "debit", "tax": "non_deductible",
     "description": "Annual depreciation charge. NOT tax-deductible in the UK — capital allowances are claimed instead. Added back in the CT computation."},

    # Non-Deductible Expenses (7300-7399)
    {"code": "7300", "name": "Entertainment (Client)", "type": "expense", "subtype": "entertainment",
     "balance": "debit", "tax": "non_deductible",
     "description": "Client entertaining — meals, drinks, events with clients. NEVER deductible for corporation tax. VAT also not recoverable."},

    {"code": "7310", "name": "Gifts & Donations", "type": "expense", "subtype": "entertainment",
     "balance": "debit", "tax": "non_deductible",
     "description": "Gifts to clients (unless < £50 with company branding). Charitable donations may qualify for CT relief if to registered UK charity."},

    {"code": "7320", "name": "Fines & Penalties", "type": "expense", "subtype": "non_deductible",
     "balance": "debit", "tax": "non_deductible",
     "description": "Parking fines, HMRC penalties, speeding tickets, late filing fees. NEVER deductible."},

    # Other Expenses (7400-7999)
    {"code": "7400", "name": "Sundry Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Miscellaneous small expenses that don't fit elsewhere. Keep this low — most items should have a proper category."},

    {"code": "7500", "name": "Bad Debts Written Off", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Invoices you've given up collecting. Deductible when 'impaired' (i.e., you've tried to collect and failed). General provisions are not deductible."},

    {"code": "7510", "name": "Doubtful Debt Provision", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "non_deductible",
     "description": "General provision for debts that might not be paid. Not deductible for CT — only specific write-offs are."},

    {"code": "7600", "name": "Use of Home as Office", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Proportion of home costs claimed for business use. HMRC simplified method: £6/week (£26/month). Or calculate actual proportion."},

    {"code": "7700", "name": "Company Formation Costs", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "Companies House incorporation fee, company secretary setup. One-off cost, fully deductible."},

    {"code": "7800", "name": "Research & Development", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible",
     "description": "R&D expenditure. May qualify for enhanced R&D tax relief (130% deduction for SMEs). Track separately."},
]


SOLE_TRADER_UK: List[Dict] = [
    # Simpler structure for sole traders — no share capital, no corporation tax

    # Assets
    {"code": "1000", "name": "Business Bank Account", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Main business bank account."},
    {"code": "1010", "name": "Petty Cash", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Cash float for small expenses."},
    {"code": "1100", "name": "Trade Debtors", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Money owed by customers."},
    {"code": "1200", "name": "Prepayments", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Amounts paid in advance."},
    {"code": "1300", "name": "Stock", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Goods held for resale."},
    {"code": "1400", "name": "Equipment", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized", "description": "Business tools and equipment."},
    {"code": "1410", "name": "Computer Equipment", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized", "description": "Laptops, monitors, printers."},
    {"code": "1420", "name": "Motor Vehicles", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized", "description": "Business vehicles."},
    {"code": "1500", "name": "Accumulated Depreciation", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a", "description": "Total depreciation to date."},

    # Liabilities
    {"code": "2000", "name": "Trade Creditors", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Money owed to suppliers."},
    {"code": "2100", "name": "VAT Control Account", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Net VAT position with HMRC."},
    {"code": "2110", "name": "VAT Input", "type": "liability", "subtype": "current_liability",
     "balance": "debit", "tax": "n/a", "description": "VAT paid on purchases."},
    {"code": "2120", "name": "VAT Output", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "VAT charged on sales."},
    {"code": "2200", "name": "Tax Liability", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Income tax and Class 4 NI owed on profits."},
    {"code": "2400", "name": "Accruals", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Expenses incurred but not yet invoiced."},
    {"code": "2500", "name": "Credit Card", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Business credit card balance."},
    {"code": "2600", "name": "Bank Loan", "type": "liability", "subtype": "long_term_liability",
     "balance": "credit", "tax": "n/a", "description": "Business loans."},

    # Equity (Sole Trader — no shares)
    {"code": "3000", "name": "Capital Introduced", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a", "description": "Money you've put INTO the business from personal funds."},
    {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a", "description": "Accumulated profits."},
    {"code": "3200", "name": "Drawings", "type": "equity", "subtype": "equity",
     "balance": "debit", "tax": "n/a", "description": "Money you've taken OUT of the business for personal use. Not an expense — reduces equity."},

    # Revenue
    {"code": "4000", "name": "Sales Revenue", "type": "revenue", "subtype": "operating_revenue",
     "balance": "credit", "tax": "n/a", "description": "Main trading income."},
    {"code": "4100", "name": "Other Income", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a", "description": "Non-trading income."},
    {"code": "4200", "name": "Interest Received", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a", "description": "Bank interest."},

    # Cost of Sales
    {"code": "5000", "name": "Cost of Sales", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible", "description": "Direct costs of goods/services sold."},
    {"code": "5010", "name": "Materials", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible", "description": "Raw materials and components."},

    # Expenses
    {"code": "6100", "name": "Rent", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible", "description": "Business premises rent."},
    {"code": "6120", "name": "Light & Heat", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible", "description": "Electricity, gas, water."},
    {"code": "6200", "name": "Insurance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Business insurance."},
    {"code": "6300", "name": "Repairs & Maintenance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Equipment and premises repairs."},
    {"code": "6400", "name": "Motor Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Fuel, servicing, road tax."},
    {"code": "6500", "name": "Travel & Subsistence", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Business travel costs."},
    {"code": "6600", "name": "Telephone & Internet", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Phone and broadband."},
    {"code": "6700", "name": "Postage & Stationery", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Stamps, envelopes, paper."},
    {"code": "6800", "name": "Advertising", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Marketing and advertising."},
    {"code": "6900", "name": "Accountancy Fees", "type": "expense", "subtype": "professional_fees",
     "balance": "debit", "tax": "deductible", "description": "Accountant and bookkeeper fees."},
    {"code": "7000", "name": "Bank Charges", "type": "expense", "subtype": "finance_costs",
     "balance": "debit", "tax": "deductible", "description": "Bank fees and card charges."},
    {"code": "7100", "name": "Software Subscriptions", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "SaaS and software costs."},
    {"code": "7200", "name": "Depreciation", "type": "expense", "subtype": "depreciation",
     "balance": "debit", "tax": "non_deductible", "description": "Annual depreciation charge. Capital allowances claimed instead."},
    {"code": "7300", "name": "Entertainment", "type": "expense", "subtype": "entertainment",
     "balance": "debit", "tax": "non_deductible", "description": "Client entertainment — not deductible."},
    {"code": "7400", "name": "Sundry Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Miscellaneous expenses."},
    {"code": "7500", "name": "Bad Debts", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Debts written off."},
    {"code": "7600", "name": "Use of Home as Office", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Home office costs — £6/week simplified or actual proportion."},
]


MICRO_ENTITY_UK: List[Dict] = [
    # Minimal accounts required under FRS 105 (turnover < £632k, balance sheet < £316k, < 10 employees)
    # Micro-entities file abbreviated accounts with no P&L on public record

    # Assets
    {"code": "1000", "name": "Cash at Bank", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Business bank account."},
    {"code": "1010", "name": "Petty Cash", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Cash float."},
    {"code": "1100", "name": "Trade Debtors", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Money owed by customers."},
    {"code": "1200", "name": "Prepayments", "type": "asset", "subtype": "current_asset",
     "balance": "debit", "tax": "n/a", "description": "Payments made in advance."},
    {"code": "1400", "name": "Equipment", "type": "asset", "subtype": "fixed_asset",
     "balance": "debit", "tax": "capitalized", "description": "Business equipment."},
    {"code": "1500", "name": "Accumulated Depreciation", "type": "asset", "subtype": "contra_asset",
     "balance": "credit", "tax": "n/a", "description": "Total depreciation to date."},

    # Liabilities
    {"code": "2000", "name": "Trade Creditors", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Money owed to suppliers."},
    {"code": "2100", "name": "VAT Control Account", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "VAT owed to/from HMRC."},
    {"code": "2200", "name": "PAYE & NI Liability", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "PAYE/NI owed to HMRC."},
    {"code": "2300", "name": "Corporation Tax", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "CT owed."},
    {"code": "2400", "name": "Accruals", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Expenses incurred but not invoiced."},
    {"code": "2500", "name": "Director's Loan Account", "type": "liability", "subtype": "current_liability",
     "balance": "credit", "tax": "n/a", "description": "Balance between director and company."},

    # Equity
    {"code": "3000", "name": "Share Capital", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a", "description": "Nominal share value."},
    {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": "equity",
     "balance": "credit", "tax": "n/a", "description": "Accumulated profits."},
    {"code": "3200", "name": "Dividends Paid", "type": "equity", "subtype": "equity",
     "balance": "debit", "tax": "n/a", "description": "Dividends to shareholders."},

    # Revenue
    {"code": "4000", "name": "Sales Revenue", "type": "revenue", "subtype": "operating_revenue",
     "balance": "credit", "tax": "n/a", "description": "Main trading income."},
    {"code": "4100", "name": "Other Income", "type": "revenue", "subtype": "other_revenue",
     "balance": "credit", "tax": "n/a", "description": "Non-trading income."},

    # Cost of Sales
    {"code": "5000", "name": "Cost of Sales", "type": "expense", "subtype": "cost_of_sales",
     "balance": "debit", "tax": "deductible", "description": "Direct costs."},

    # Expenses (condensed for micro-entity)
    {"code": "6000", "name": "Wages & Salaries", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible", "description": "Staff wages."},
    {"code": "6010", "name": "Employer's NI", "type": "expense", "subtype": "staff_costs",
     "balance": "debit", "tax": "deductible", "description": "Employer NI contributions."},
    {"code": "6100", "name": "Rent & Rates", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible", "description": "Office rent and business rates."},
    {"code": "6120", "name": "Utilities", "type": "expense", "subtype": "premises_costs",
     "balance": "debit", "tax": "deductible", "description": "Gas, electric, water."},
    {"code": "6200", "name": "Insurance", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Business insurance."},
    {"code": "6400", "name": "Motor Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Vehicle costs."},
    {"code": "6500", "name": "Travel", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Business travel."},
    {"code": "6600", "name": "Telephone & Internet", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Phone and broadband."},
    {"code": "6800", "name": "Advertising", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Marketing costs."},
    {"code": "6900", "name": "Professional Fees", "type": "expense", "subtype": "professional_fees",
     "balance": "debit", "tax": "deductible", "description": "Accountant and legal fees."},
    {"code": "7000", "name": "Bank Charges", "type": "expense", "subtype": "finance_costs",
     "balance": "debit", "tax": "deductible", "description": "Bank fees."},
    {"code": "7100", "name": "Software", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Software subscriptions."},
    {"code": "7200", "name": "Depreciation", "type": "expense", "subtype": "depreciation",
     "balance": "debit", "tax": "non_deductible", "description": "Depreciation charge."},
    {"code": "7400", "name": "Sundry Expenses", "type": "expense", "subtype": "admin_expenses",
     "balance": "debit", "tax": "deductible", "description": "Miscellaneous."},
]


# ============================================================
# TEMPLATE REGISTRY
# ============================================================
TEMPLATES = {
    "limited_company_uk": {
        "name": "UK Limited Company (FRS 102)",
        "description": "Full chart of accounts for a UK limited company following FRS 102 Section 1A. Includes VAT accounts, PAYE, director's loan, corporation tax, and detailed expense categories with HMRC tax treatment.",
        "accounts": LIMITED_COMPANY_UK,
    },
    "sole_trader_uk": {
        "name": "UK Sole Trader",
        "description": "Simplified chart of accounts for a sole trader. Uses drawings instead of dividends, capital introduced instead of share capital. No corporation tax — profits taxed via Self Assessment.",
        "accounts": SOLE_TRADER_UK,
    },
    "micro_entity_uk": {
        "name": "UK Micro-Entity (FRS 105)",
        "description": "Minimal chart of accounts for micro-entities (turnover < £632k). Condensed expense categories. Files abbreviated accounts at Companies House.",
        "accounts": MICRO_ENTITY_UK,
    },
}


# ============================================================
# SERVICE CLASS
# ============================================================

class COATemplateService:
    """Service for seeding chart of accounts from templates."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def list_templates() -> list:
        """Return available templates (without the full account lists)."""
        return [
            {
                "key": key,
                "name": tmpl["name"],
                "description": tmpl["description"],
                "account_count": len(tmpl["accounts"]),
            }
            for key, tmpl in TEMPLATES.items()
        ]

    def seed_template(
        self,
        company_id: str,
        template_key: str,
        clear_existing: bool = False,
    ) -> dict:
        """
        Seed a company's chart of accounts from a template.

        Args:
            company_id: The company to seed accounts for
            template_key: One of 'limited_company_uk', 'sole_trader_uk', 'micro_entity_uk'
            clear_existing: If True, deactivate existing accounts first

        Returns:
            dict with 'created' count and 'skipped' count (if account code already exists)
        """
        if template_key not in TEMPLATES:
            available = ", ".join(TEMPLATES.keys())
            raise ValueError(
                f"Unknown template '{template_key}'. Available: {available}"
            )

        template = TEMPLATES[template_key]

        # Optionally deactivate existing accounts
        if clear_existing:
            existing = Account.get_company_accounts(
                self.db, company_id, active_only=True
            )
            for account in existing:
                account.is_active = False
            self.db.commit()

        created = 0
        skipped = 0

        for acc in template["accounts"]:
            # Check if account code already exists for this company
            existing = Account.get_by_code(self.db, company_id, acc["code"])
            if existing:
                skipped += 1
                continue

            account = Account(
                company_id=company_id,
                account_code=acc["code"],
                account_name=acc["name"],
                account_type=acc["type"],
                account_subtype=acc.get("subtype"),
                normal_balance=acc["balance"],
                tax_treatment=acc.get("tax"),
                description=acc.get("description"),
                is_active=True,
            )
            account.save(self.db)
            created += 1

        return {
            "template": template_key,
            "template_name": template["name"],
            "created": created,
            "skipped": skipped,
            "total_in_template": len(template["accounts"]),
        }
