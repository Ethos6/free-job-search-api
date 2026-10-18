"""Company job boards the index starts with. Every entry was checked to return open jobs
from its public API in October 2026. The directory grows by itself: boards found through
web search and in job posts are added automatically, and you can add your own with
JOBS_COMPANIES="greenhouse:acme,lever:example".
"""

SEED_BOARDS: dict[str, list[str]] = {
    "greenhouse": [
        "abcellera", "adyen", "affirm", "airbnb", "airtable", "anthropic", "asana", "block", "brex", "calendly",
        "carta", "celonis", "chime", "cloudflare", "cloverhealth", "coinbase", "contentful", "coursera",
        "cultureamp", "databricks", "datadog", "deliveroo", "discord", "doximity", "dropbox", "duolingo", "elastic",
        "epicgames", "faire", "figma", "fivetran", "flexport", "gitlab", "groww", "gusto", "hellofresh",
        "instacart", "intercom", "jetbrains", "khanacademy", "lyft", "masterclass", "mercury", "mixpanel",
        "modernhealth", "mongodb", "monzo", "n26", "netlify", "newrelic", "nextdoor", "nuro", "okta", "onemedical",
        "oscar", "pagerduty", "peloton", "pinterest", "reddit", "relativity", "riotgames", "robinhood", "roblox",
        "samsara", "scaleai", "scopely", "spacex", "squarespace", "stripe", "sumup", "talkspace", "toast",
        "trivago", "twilio", "twitch", "udemy", "vercel", "waymo", "wise", "zocdoc",
    ],
    "lever": [
        "appen", "binance", "cred", "greenlight", "jumpcloud", "meesho", "neon", "outreach", "palantir", "paytm",
        "rws", "scaleway", "shieldai", "spotify", "wealthfront", "zeta", "zoox",
    ],
    "ashby": [
        "airbyte", "airwallex", "amplitude", "apify", "ashby", "astronomer", "attio", "baseten", "browserbase",
        "clickup", "cohere", "cursor", "drata", "elevenlabs", "fireworks", "fullstory", "hex", "langchain", "linear",
        "llamaindex", "merge", "modal", "notion", "openai", "perplexity", "pinecone", "plaid", "plane", "posthog",
        "prefect", "ramp", "replit", "secureframe", "sentry", "supabase", "vanta", "warp", "wealthsimple",
        "webflow", "zapier",
    ],
    "workable": ["seeq"],
    "recruitee": ["allright"],
    "smartrecruiters": [
        "Accor", "Aramark", "BoschGroup", "Canva", "Continental", "Endava", "Equinox", "Securitas", "Sodexo",
        "Ubisoft2",
    ],
}
