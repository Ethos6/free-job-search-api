"""Words the built-in parser and the ranker understand.

Skills and roles are stored as canonical name -> aliases. Matching is case-insensitive
and on word boundaries, so "js" matches "JS" but not "jsx" (which has its own entry).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

SKILLS: dict[str, list[str]] = {
    # programming languages
    "python": ["py", "python3"], "java": [], "javascript": ["js", "ecmascript", "es6"],
    "typescript": ["ts"], "go": ["golang"], "rust": [], "c": [], "c++": ["cpp", "c plus plus"],
    "c#": ["csharp", "c sharp"], "ruby": [], "php": [], "kotlin": [], "swift": [], "scala": [],
    "r": [], "julia": [], "dart": [], "elixir": [], "erlang": [], "haskell": [], "clojure": [],
    "perl": [], "lua": [], "matlab": [], "objective-c": ["objective c", "objc"], "f#": ["fsharp"],
    "zig": [], "solidity": [], "cobol": [], "fortran": [], "bash": ["shell scripting", "shell"],
    "powershell": [], "sql": [], "graphql": [], "grpc": [], "rest api": ["rest apis", "restful", "rest"], "protobuf": [], "html": ["html5"], "css": ["css3"],
    # web and mobile frameworks
    "react": ["react.js", "reactjs"], "react native": [], "next.js": ["nextjs"], "vue": ["vue.js", "vuejs"],
    "nuxt": [], "angular": ["angularjs"], "svelte": ["sveltekit"], "jquery": [], "tailwind": ["tailwindcss"],
    "node.js": ["node", "nodejs"], "express": ["express.js"], "nestjs": ["nest.js"], "deno": [], "bun": [],
    "django": [], "flask": [], "fastapi": [], "rails": ["ruby on rails", "ror"], "laravel": [],
    "symfony": [], "spring": ["spring boot", "springboot"], ".net": ["dotnet", "asp.net", ".net core"],
    "flutter": [], "android": [], "ios": [], "swiftui": [], "jetpack compose": [], "electron": [],
    "unity": [], "unreal engine": ["unreal"], "godot": [], "wordpress": [], "shopify": [], "webflow": [],
    # data and ai
    "machine learning": ["ml"], "deep learning": [], "artificial intelligence": ["ai"],
    "llm": ["llms", "large language models", "genai", "generative ai"], "nlp": ["natural language processing"],
    "computer vision": ["cv"], "pytorch": [], "tensorflow": [], "keras": [], "jax": [],
    "scikit-learn": ["sklearn", "scikit learn"], "pandas": [], "numpy": [], "spark": ["apache spark", "pyspark"],
    "hadoop": [], "kafka": ["apache kafka"], "airflow": ["apache airflow"], "dbt": [], "snowflake": [],
    "databricks": [], "bigquery": [], "redshift": [], "tableau": [], "power bi": ["powerbi"], "looker": [],
    "excel": ["microsoft excel", "spreadsheets"], "statistics": [], "data analysis": ["data analytics"],
    "data engineering": [], "data science": [], "etl": [], "mlops": [], "langchain": [], "rag": [],
    "hugging face": ["huggingface"], "openai": [], "prompt engineering": [], "a/b testing": ["ab testing"],
    # databases
    "postgresql": ["postgres", "psql"], "mysql": [], "mariadb": [], "sqlite": [], "mongodb": ["mongo"],
    "redis": [], "elasticsearch": ["elastic search", "opensearch"], "cassandra": [], "dynamodb": [],
    "oracle": [], "sql server": ["mssql", "microsoft sql server"], "neo4j": [], "clickhouse": [],
    # cloud and devops
    "aws": ["amazon web services"], "azure": ["microsoft azure"], "gcp": ["google cloud", "google cloud platform"],
    "docker": [], "kubernetes": ["k8s"], "terraform": [], "ansible": [], "helm": [], "jenkins": [],
    "github actions": [], "gitlab ci": [], "ci/cd": ["cicd", "ci cd"], "linux": [], "nginx": [],
    "serverless": ["lambda"], "microservices": [], "devops": [], "sre": ["site reliability"],
    "prometheus": [], "grafana": [], "datadog": [], "git": [], "networking": [], "vmware": [],
    # security
    "cybersecurity": ["cyber security", "infosec", "information security"], "penetration testing": ["pentesting", "pen testing"],
    "siem": [], "soc": [], "iam": ["identity and access management"], "cloud security": [], "appsec": ["application security"],
    "incident response": [], "threat intelligence": [], "iso 27001": [], "soc 2": ["soc2"], "gdpr": [],
    # design and product
    "figma": [], "sketch": [], "adobe xd": [], "photoshop": [], "illustrator": [], "indesign": [],
    "after effects": [], "premiere pro": [], "blender": [], "ui design": ["ui"], "ux design": ["ux", "user experience"],
    "user research": [], "product management": [], "agile": [], "scrum": [], "jira": [], "roadmapping": [],
    # marketing, sales, business
    "seo": ["search engine optimization"], "sem": ["google ads", "ppc", "paid search"], "content marketing": [],
    "copywriting": [], "social media": [], "email marketing": [], "marketing automation": [], "hubspot": [],
    "salesforce": ["sfdc"], "crm": [], "b2b sales": [], "saas sales": [], "account management": [],
    "business development": ["bizdev"], "lead generation": [], "negotiation": [], "customer success": [],
    "customer support": ["customer service"], "zendesk": [], "growth marketing": [], "brand marketing": [],
    "public relations": ["pr"], "market research": [], "google analytics": ["ga4"], "ecommerce": ["e-commerce"],
    # finance, legal, operations, people
    "accounting": [], "bookkeeping": [], "financial modeling": ["financial modelling"], "fp&a": ["fpa"],
    "audit": ["auditing"], "tax": ["taxation"], "ifrs": [], "gaap": ["us gaap"], "sap": [], "quickbooks": [],
    "xero": [], "payroll": [], "treasury": [], "risk management": [], "compliance": [], "aml": ["kyc"],
    "investment banking": [], "private equity": [], "venture capital": [], "trading": [], "underwriting": [],
    "contract law": [], "corporate law": [], "litigation": [], "paralegal": [], "legal research": [],
    "supply chain": [], "logistics": [], "procurement": [], "project management": ["pmp"], "operations": [],
    "lean": ["six sigma", "lean six sigma"], "recruiting": ["recruitment", "talent acquisition"],
    "hr": ["human resources", "people operations"], "employee relations": [], "training": [],
    # healthcare and science
    "nursing": ["rn", "registered nurse"], "patient care": [], "emr": ["ehr", "epic", "cerner"],
    "pharmacy": [], "clinical research": [], "clinical trials": [], "medical coding": [], "phlebotomy": [],
    "physiotherapy": ["physical therapy"], "radiology": [], "laboratory": ["lab work"], "biology": [],
    "chemistry": [], "bioinformatics": [], "molecular biology": [], "crispr": [], "gmp": [], "regulatory affairs": [],
    # engineering and trades
    "autocad": [], "solidworks": [], "catia": [], "revit": [], "cad": [], "plc": [], "embedded": ["embedded systems"],
    "fpga": [], "vhdl": [], "verilog": [], "pcb design": [], "robotics": [], "ros": [], "electrical engineering": [],
    "mechanical engineering": [], "civil engineering": [], "hvac": [], "welding": [], "cnc": [],
    # education, writing, languages
    "teaching": [], "curriculum design": [], "tutoring": [], "technical writing": [], "editing": [],
    "translation": [], "journalism": [], "video editing": [], "photography": [], "animation": [],
}

# Roles: canonical title -> other ways to say it. Used to read the request and to match job titles.
ROLES: dict[str, list[str]] = {
    "software engineer": ["software developer", "programmer", "developer", "sde", "swe", "software dev"],
    "backend engineer": ["backend developer", "back-end engineer", "back-end developer", "back end developer",
                         "server-side developer", "api developer"],
    "frontend engineer": ["frontend developer", "front-end engineer", "front-end developer", "front end developer",
                          "ui engineer", "ui developer", "web developer"],
    "full stack engineer": ["full stack developer", "fullstack developer", "full-stack developer",
                            "fullstack engineer", "full-stack engineer"],
    "mobile engineer": ["mobile developer", "ios developer", "ios engineer", "android developer",
                        "android engineer", "app developer", "flutter developer", "react native developer"],
    "devops engineer": ["devops", "platform engineer", "infrastructure engineer", "cloud engineer",
                        "site reliability engineer", "sre", "build engineer", "release engineer"],
    "data engineer": ["big data engineer", "etl developer", "analytics engineer"],
    "data scientist": ["ml scientist", "research scientist", "applied scientist", "decision scientist"],
    "data analyst": ["business analyst", "bi analyst", "analytics analyst", "reporting analyst",
                     "business intelligence analyst", "insights analyst"],
    "machine learning engineer": ["ml engineer", "ai engineer", "mlops engineer", "deep learning engineer",
                                  "llm engineer", "nlp engineer", "computer vision engineer", "ai developer"],
    "security engineer": ["cybersecurity engineer", "security analyst", "soc analyst", "penetration tester",
                          "pentester", "appsec engineer", "information security analyst", "security architect"],
    "qa engineer": ["qa", "test engineer", "sdet", "quality assurance engineer", "automation tester",
                    "software tester", "qa analyst"],
    "embedded engineer": ["embedded software engineer", "firmware engineer", "embedded developer"],
    "game developer": ["game programmer", "gameplay programmer", "game engineer", "unity developer"],
    "blockchain engineer": ["blockchain developer", "smart contract developer", "web3 developer",
                            "solidity developer"],
    "solutions architect": ["software architect", "cloud architect", "enterprise architect",
                            "technical architect", "solution architect"],
    "engineering manager": ["software engineering manager", "head of engineering", "vp engineering",
                            "director of engineering", "cto"],
    "tech lead": ["technical lead", "lead engineer", "lead developer", "team lead"],
    "it support": ["it support specialist", "help desk", "helpdesk", "desktop support", "it technician",
                   "system administrator", "sysadmin", "it administrator", "network engineer",
                   "network administrator"],
    "database administrator": ["dba"],
    "product manager": ["product owner", "pm", "technical product manager", "group product manager",
                        "head of product", "vp product"],
    "project manager": ["program manager", "delivery manager", "scrum master", "project coordinator",
                        "technical program manager"],
    "product designer": ["ux designer", "ui designer", "ui/ux designer", "ux/ui designer", "interaction designer",
                         "ux researcher", "user researcher", "visual designer", "web designer"],
    "graphic designer": ["designer", "brand designer", "motion designer", "illustrator", "creative designer",
                         "art director"],
    "marketing manager": ["marketing specialist", "digital marketing manager", "digital marketer",
                          "growth marketer", "growth manager", "performance marketer", "marketing executive",
                          "head of marketing", "cmo", "brand manager", "product marketing manager"],
    "content writer": ["copywriter", "content strategist", "content creator", "technical writer", "editor",
                       "content marketing manager", "writer", "journalist"],
    "seo specialist": ["seo manager", "seo analyst", "sem specialist"],
    "social media manager": ["community manager", "social media specialist"],
    "sales representative": ["sales executive", "account executive", "sales associate", "sdr", "bdr",
                             "sales development representative", "business development representative",
                             "inside sales", "sales manager", "sales specialist", "salesperson"],
    "business development manager": ["business development executive", "partnerships manager",
                                     "partner manager"],
    "account manager": ["key account manager", "client manager", "relationship manager"],
    "customer success manager": ["customer success", "csm", "client success manager"],
    "customer support": ["customer support specialist", "customer service representative", "support agent",
                         "customer service", "support specialist", "call center agent", "technical support"],
    "accountant": ["staff accountant", "senior accountant", "chartered accountant", "ca", "cpa",
                   "bookkeeper", "accounts executive", "accounts payable", "accounts receivable"],
    "financial analyst": ["finance analyst", "fp&a analyst", "investment analyst", "equity analyst",
                          "credit analyst", "risk analyst", "quantitative analyst", "quant"],
    "finance manager": ["controller", "financial controller", "cfo", "head of finance", "finance director"],
    "auditor": ["internal auditor", "audit associate", "external auditor"],
    "lawyer": ["attorney", "solicitor", "counsel", "legal counsel", "associate attorney", "advocate",
               "general counsel"],
    "paralegal": ["legal assistant", "legal secretary"],
    "compliance officer": ["compliance analyst", "compliance manager", "aml analyst", "kyc analyst"],
    "hr manager": ["hr generalist", "hr business partner", "hrbp", "people partner", "hr specialist",
                   "hr executive", "human resources manager", "people operations"],
    "recruiter": ["talent acquisition specialist", "technical recruiter", "talent partner", "sourcer",
                  "headhunter"],
    "operations manager": ["operations associate", "operations specialist", "ops manager",
                           "business operations", "chief of staff"],
    "supply chain manager": ["logistics manager", "procurement manager", "buyer", "purchasing manager",
                             "logistics coordinator", "warehouse manager", "inventory manager"],
    "administrative assistant": ["executive assistant", "office manager", "receptionist", "personal assistant",
                                 "admin assistant", "office administrator", "virtual assistant"],
    "data entry": ["data entry clerk", "data entry operator"],
    "nurse": ["registered nurse", "staff nurse", "rn", "nurse practitioner", "lpn", "icu nurse"],
    "doctor": ["physician", "medical officer", "general practitioner", "gp", "resident physician", "surgeon"],
    "pharmacist": ["clinical pharmacist", "pharmacy technician"],
    "medical assistant": ["healthcare assistant", "care assistant", "caregiver", "patient care technician"],
    "therapist": ["physiotherapist", "physical therapist", "occupational therapist", "psychologist",
                  "counselor", "counsellor", "speech therapist"],
    "lab technician": ["laboratory technician", "lab scientist", "research associate", "laboratory analyst"],
    "clinical research associate": ["cra", "clinical research coordinator", "clinical trial associate"],
    "teacher": ["educator", "tutor", "instructor", "lecturer", "professor", "teaching assistant", "trainer"],
    "mechanical engineer": ["design engineer", "manufacturing engineer", "process engineer"],
    "electrical engineer": ["electronics engineer", "hardware engineer", "power engineer"],
    "civil engineer": ["structural engineer", "site engineer", "construction engineer"],
    "architect": ["architectural designer"],
    "construction manager": ["site manager", "project engineer", "foreman"],
    "electrician": ["technician", "maintenance technician", "field technician", "service technician"],
    "driver": ["delivery driver", "truck driver", "courier"],
    "chef": ["cook", "line cook", "sous chef", "kitchen staff"],
    "retail associate": ["store associate", "cashier", "sales associate", "store manager", "shop assistant"],
    "hospitality": ["hotel manager", "front desk", "guest relations", "waiter", "bartender", "barista"],
    "consultant": ["management consultant", "strategy consultant", "business consultant", "advisor"],
    "researcher": ["research scientist", "scientist", "postdoc", "research fellow"],
    "translator": ["interpreter", "localization specialist"],
    "video editor": ["videographer", "video producer", "editor"],
}

DISPLAY = {"javascript": "JavaScript", "typescript": "TypeScript", "postgresql": "PostgreSQL", "mongodb": "MongoDB",
           "node.js": "Node.js", "next.js": "Next.js", "graphql": "GraphQL", "mysql": "MySQL", "mariadb": "MariaDB",
           "github actions": "GitHub Actions", "gitlab ci": "GitLab CI", "fastapi": "FastAPI", "pytorch": "PyTorch",
           "tensorflow": "TensorFlow", "ios": "iOS", "devops": "DevOps", "fp&a": "FP&A", "ci/cd": "CI/CD",
           "a/b testing": "A/B testing", "c#": "C#", "c++": "C++", ".net": ".NET", "f#": "F#", "grpc": "gRPC",
           "rest api": "REST API", "dbt": "dbt", "jquery": "jQuery", "nestjs": "NestJS", "vue": "Vue",
           "ux design": "UX design", "ui design": "UI design", "scikit-learn": "scikit-learn", "objective-c":
           "Objective-C", "power bi": "Power BI", "bigquery": "BigQuery", "elasticsearch": "Elasticsearch",
           "dynamodb": "DynamoDB", "clickhouse": "ClickHouse", "sql server": "SQL Server", "hubspot": "HubSpot",
           "quickbooks": "QuickBooks", "autocad": "AutoCAD", "solidworks": "SolidWorks", "iso 27001": "ISO 27001",
           "soc 2": "SOC 2", "emr": "EMR", "gmp": "GMP", "ifrs": "IFRS", "gaap": "GAAP", "llm": "LLMs",
           "mlops": "MLOps", "langchain": "LangChain", "openai": "OpenAI", "hugging face": "Hugging Face",
           "macos": "macOS", "swiftui": "SwiftUI", "webflow": "Webflow", "wordpress": "WordPress"}


def display(name: str) -> str:
    """How to write a skill or keyword for people: 'postgresql' -> 'PostgreSQL', 'aws' -> 'AWS'."""
    if name in DISPLAY:
        return DISPLAY[name]
    if len(name) <= 3 and name.isalpha():
        return name.upper()
    return name[:1].upper() + name[1:]


SENIORITY_WORDS: dict[str, list[str]] = {
    "intern": ["intern", "internship", "trainee", "apprentice", "working student", "werkstudent"],
    "junior": ["junior", "jr", "jr.", "entry level", "entry-level", "graduate", "new grad", "fresher",
               "associate", "beginner"],
    "mid": ["mid level", "mid-level", "intermediate", "medior", "mid senior", "mid-senior"],
    "senior": ["senior", "sr", "sr.", "experienced"],
    "lead": ["lead", "team lead", "tech lead"],
    "principal": ["principal", "staff", "distinguished", "architect"],
    "manager": ["manager", "head of"],
    "director": ["director", "vp", "vice president"],
    "executive": ["chief", "ceo", "cto", "cfo", "coo", "cmo", "c-level", "executive"],
}

EMPLOYMENT_WORDS: dict[str, list[str]] = {
    "full_time": ["full time", "full-time", "fulltime", "permanent", "fte"],
    "part_time": ["part time", "part-time", "parttime"],
    "contract": ["contract", "contractor", "contract-to-hire", "c2h", "b2b contract"],
    "internship": ["internship", "intern"],
    "temporary": ["temporary", "temp", "seasonal", "fixed term", "fixed-term"],
    "freelance": ["freelance", "freelancer", "gig", "independent contractor"],
}

SPOKEN_LANGUAGES = ["english", "german", "french", "spanish", "portuguese", "italian", "dutch", "polish",
                    "russian", "ukrainian", "turkish", "arabic", "hebrew", "hindi", "bengali", "urdu",
                    "tamil", "telugu", "marathi", "gujarati", "kannada", "malayalam", "punjabi", "japanese",
                    "korean", "mandarin", "chinese", "cantonese", "vietnamese", "thai", "indonesian", "malay",
                    "swedish", "norwegian", "danish", "finnish", "greek", "czech", "romanian", "hungarian"]

CURRENCY_SYMBOLS = {"$": "USD", "us$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "euro": "EUR",
                    "euros": "EUR", "£": "GBP", "gbp": "GBP", "₹": "INR", "inr": "INR", "rs": "INR",
                    "rs.": "INR", "rupees": "INR", "lpa": "INR", "lakh": "INR", "lakhs": "INR", "¥": "JPY",
                    "jpy": "JPY", "cad": "CAD", "c$": "CAD", "aud": "AUD", "a$": "AUD", "chf": "CHF",
                    "sek": "SEK", "nok": "NOK", "dkk": "DKK", "pln": "PLN", "zł": "PLN", "brl": "BRL",
                    "r$": "BRL", "mxn": "MXN", "sgd": "SGD", "s$": "SGD", "aed": "AED", "dirham": "AED",
                    "zar": "ZAR", "nzd": "NZD", "hkd": "HKD", "czk": "CZK", "ils": "ILS", "₪": "ILS",
                    "try": "TRY", "₺": "TRY", "krw": "KRW", "₩": "KRW", "php": "PHP", "₱": "PHP",
                    "ngn": "NGN", "₦": "NGN", "kes": "KES", "egp": "EGP", "pkr": "PKR", "idr": "IDR",
                    "myr": "MYR", "thb": "THB", "vnd": "VND", "huf": "HUF", "ron": "RON", "sar": "SAR"}

# Approximate value of 1 unit in US dollars. Only used to compare salaries written in
# different currencies, and every such comparison is labelled "approximate".
# Override with JOBS_FX_RATES='{"EUR": 1.1, ...}'.
FX_TO_USD = {"USD": 1.0, "EUR": 1.1, "GBP": 1.3, "INR": 0.012, "JPY": 0.0068, "CAD": 0.73,
             "AUD": 0.66, "CHF": 1.15, "SEK": 0.095, "NOK": 0.094, "DKK": 0.147, "PLN": 0.25,
             "BRL": 0.18, "MXN": 0.054, "SGD": 0.76, "AED": 0.272, "ZAR": 0.055, "NZD": 0.6,
             "HKD": 0.128, "CZK": 0.044, "ILS": 0.27, "TRY": 0.025, "KRW": 0.00073, "PHP": 0.017,
             "NGN": 0.00065, "KES": 0.0077, "EGP": 0.02, "PKR": 0.0036, "IDR": 0.000062, "MYR": 0.23,
             "THB": 0.029, "VND": 0.00004, "HUF": 0.0028, "RON": 0.22, "SAR": 0.267}

# Regions people write in requests and in remote-job restrictions -> how to build their countries.
MIDDLE_EAST = {"AE", "SA", "IL", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "IR", "SY", "YE", "PS", "TR", "EG"}
EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
      "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
SOUTHEAST_ASIA = {"SG", "MY", "ID", "TH", "VN", "PH", "MM", "KH", "LA", "BN", "TL"}
REGION_RULES: dict[str, tuple[set[str], set[str], set[str]]] = {
    # word: (continents to include, extra countries, countries to remove)
    "europe": ({"europe"}, set(), set()), "european": ({"europe"}, set(), set()),
    "eu": (set(), EU, set()),
    "eea": (set(), EU | {"IS", "LI", "NO"}, set()),
    "emea": ({"europe", "africa"}, MIDDLE_EAST, set()),
    "north america": ({"north america"}, set(), set()),
    "us and canada": (set(), {"US", "CA"}, set()), "usa and canada": (set(), {"US", "CA"}, set()),
    "americas": ({"north america", "south america"}, set(), set()),
    "latam": ({"south america", "north america"}, set(), {"US", "CA", "GL", "BM", "PM"}),
    "latin america": ({"south america", "north america"}, set(), {"US", "CA", "GL", "BM", "PM"}),
    "south america": ({"south america"}, set(), set()),
    "asia": ({"asia"}, set(), set()), "apac": ({"asia", "oceania"}, set(), MIDDLE_EAST),
    "asia pacific": ({"asia", "oceania"}, set(), MIDDLE_EAST),
    "southeast asia": (set(), SOUTHEAST_ASIA, set()), "middle east": (set(), MIDDLE_EAST, set()),
    "africa": ({"africa"}, set(), set()), "oceania": ({"oceania"}, set(), set()),
    "anz": (set(), {"AU", "NZ"}, set()), "australia and new zealand": (set(), {"AU", "NZ"}, set()),
    "nordics": (set(), {"SE", "NO", "DK", "FI", "IS"}, set()),
    "dach": (set(), {"DE", "AT", "CH"}, set()), "benelux": (set(), {"BE", "NL", "LU"}, set()),
}
WORLDWIDE_WORDS = ["worldwide", "anywhere", "global", "globally", "any location", "anywhere in the world",
                   "work from anywhere", "fully distributed"]


@lru_cache(maxsize=1)
def places() -> dict:
    with resources.files("jobsearch").joinpath("data/places.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def country_names() -> dict[str, str]:
    """lower-case name -> ISO code."""
    out = {}
    for code, names in places()["countries"].items():
        for n in names:
            out[n] = code
    return out


@lru_cache(maxsize=1)
def region_countries() -> dict[str, set[str]]:
    """region word -> set of ISO codes (e.g. 'eu' -> EU countries)."""
    by_continent: dict[str, set[str]] = {}
    for code, cont in places()["continents"].items():
        by_continent.setdefault(cont, set()).add(code)
    out = {}
    for word, (continents, extra, remove) in REGION_RULES.items():
        codes: set[str] = set(extra)
        for c in continents:
            codes |= by_continent.get(c, set())
        out[word] = codes - remove
    return out


def alias_pattern(words: list[str]) -> re.Pattern:
    """Regex matching any of the words as whole words, longest first."""
    parts = sorted({w for w in words if w}, key=len, reverse=True)
    return re.compile(r"(?<![\w+#.])(" + "|".join(re.escape(p) for p in parts) + r")(?![\w+#])", re.I)


@lru_cache(maxsize=1)
def skill_lookup() -> tuple[re.Pattern, dict[str, str]]:
    canon = {}
    for name, aliases in SKILLS.items():
        canon[name] = name
        for a in aliases:
            canon[a] = name
    return alias_pattern(list(canon)), canon


@lru_cache(maxsize=1)
def role_lookup() -> tuple[re.Pattern, dict[str, str]]:
    canon = {}
    for name, aliases in ROLES.items():
        canon[name] = name
        for a in aliases:
            canon.setdefault(a, name)
    return alias_pattern(list(canon)), canon


def find_skills(text: str) -> list[str]:
    pat, canon = skill_lookup()
    out: list[str] = []
    for m in pat.finditer(text):
        word = m.group(1)
        # single letters (c, r) and short ambiguous words only count when written as-is
        if word.lower() in ("c", "r", "go", "ai", "ui", "ux", "ml", "cv", "pr", "rn", "soc", "sea", "ts",
                            "shell", "lean", "training", "operations", "tax", "audit") and not _strict_ok(text, m):
            continue
        name = canon[word.lower()]
        if name not in out:
            out.append(name)
    return out


def _strict_ok(text: str, m: re.Match) -> bool:
    word = m.group(1)
    if word.lower() in ("c", "r"):
        # "C", "R" only as standalone capital letters in a list context, e.g. "C, C++ and R"
        return word.isupper() and bool(re.search(r"[,/(]|\band\b|\bor\b", text[max(0, m.start() - 4):m.end() + 5]))
    if word.lower() == "go":
        return word == "Go" or bool(re.search(r"\b(golang|go developer|go engineer|in go)\b", text, re.I))
    if word.lower() in ("ai", "ui", "ux", "ml", "cv", "pr", "rn", "soc", "ts"):
        return word.isupper()
    if word.lower() == "sea":
        return word.isupper()
    return True  # multi-letter generic words are fine in requests


def find_roles(text: str) -> list[str]:
    pat, canon = role_lookup()
    out: list[str] = []
    for m in pat.finditer(text):
        word = m.group(1)
        if word.lower() in ("pm", "ca", "gp", "cra", "rn", "qa", "sre", "sde", "swe", "csm", "sdr", "bdr", "dba",
                            "quant") and not word.isupper() and word.lower() not in ("quant",):
            continue
        name = canon[word.lower()]
        if name not in out:
            out.append(name)
    return out


def role_terms(role: str) -> list[str]:
    """All the ways a canonical role (or any free-text title) may appear in job titles."""
    role = role.lower()
    if role in ROLES:
        return [role] + ROLES[role]
    _, canon = role_lookup()
    if role in canon:
        c = canon[role]
        return [role, c] + [a for a in ROLES[c] if a != role]
    return [role]
