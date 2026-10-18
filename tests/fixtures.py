"""Sample responses with the same shapes as the real APIs (field names captured from the live
endpoints in October 2026; values shortened)."""
from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def ts(days_ago: float) -> int:
    return int((NOW - timedelta(days=days_ago)).timestamp())


GREENHOUSE = {
    "jobs": [
        {"absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1001", "data_compliance": [],
         "internal_job_id": 1, "location": {"name": "Remote, Europe"}, "metadata": [
             {"id": 1, "name": "Employment Type", "value": "Full-time", "value_type": "single_select"}],
         "id": 1001, "updated_at": iso(2), "requisition_id": "R1", "title": "Senior Backend Engineer (Python)",
         "company_name": "Acme", "first_published": iso(3), "language": "en",
         "content": "&lt;p&gt;We build APIs in &lt;strong&gt;Python&lt;/strong&gt; with Django and PostgreSQL on AWS. "
                    "Kubernetes is a plus.&lt;/p&gt;",
         "departments": [{"id": 1, "name": "Engineering"}], "offices": [{"id": 1, "name": "Remote", "location": "Europe"}],
         "pay_input_ranges": [{"min_cents": 9000000, "max_cents": 12000000, "currency_type": "EUR",
                               "title": "Europe range"}]},
        {"absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1002", "location": {"name": "San Francisco, CA"},
         "id": 1002, "updated_at": iso(40), "title": "Account Executive", "company_name": "Acme",
         "first_published": iso(40), "content": "&lt;p&gt;Sell our product. Cold calling.&lt;/p&gt;",
         "metadata": [], "departments": [{"name": "Sales"}], "offices": []},
        {"absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1003", "location": {"name": "Berlin, Germany"},
         "id": 1003, "updated_at": iso(1), "title": "Backend Developer", "company_name": "Acme",
         "first_published": iso(1), "content": "&lt;p&gt;Python, FastAPI, Kafka. Hybrid, 2 days in our Berlin office.&lt;/p&gt;",
         "metadata": [], "departments": [], "offices": []},
    ],
    "meta": {"total": 3},
}

LEVER = [
    {"additionalPlain": "We offer equity.", "additional": "", "categories": {
        "commitment": "Permanent", "department": "Engineering", "location": "Mexico City", "team": "Platform",
        "allLocations": ["Mexico City"]},
     "createdAt": int((NOW - timedelta(days=5)).timestamp() * 1000), "descriptionPlain": "Build services in Go.",
     "description": "", "id": "abc", "lists": [{"text": "What You'll Do", "content": "<li>Go and gRPC</li>"}],
     "text": "Software Engineer, Platform", "country": "MX", "workplaceType": "hybrid", "opening": "",
     "openingPlain": "", "descriptionBody": "", "descriptionBodyPlain": "",
     "hostedUrl": "https://jobs.lever.co/spotify/abc", "applyUrl": "https://jobs.lever.co/spotify/abc/apply",
     "salaryRange": {"min": 50000, "max": 70000, "currency": "USD", "interval": "per-year-salary"}},
]

ASHBY = {
    "apiVersion": "1",
    "jobs": [{"id": "j1", "title": "Data Analyst", "department": "Finance", "team": "Analytics",
              "employmentType": "FullTime", "location": "New York, NY (HQ)", "shouldDisplayCompensationOnJobPostings": True,
              "secondaryLocations": [{"location": "Remote (US)", "address": {"postalAddress": {"addressCountry": "United States"}}}],
              "publishedAt": iso(2), "isListed": True, "isRemote": True, "workplaceType": "Hybrid",
              "address": {"postalAddress": {"addressRegion": "NY", "addressCountry": "USA",
                                            "addressLocality": "New York City"}},
              "jobUrl": "https://jobs.ashbyhq.com/ramp/j1", "applyUrl": "https://jobs.ashbyhq.com/ramp/j1/application",
              "descriptionHtml": "<p>SQL and Tableau</p>", "descriptionPlain": "SQL, Excel and Tableau dashboards.",
              "compensation": {"compensationTierSummary": "$90K – $120K", "compensationTiers": [{"components": [
                  {"id": "e", "summary": "Offers Equity", "compensationType": "EquityPercentage", "interval": "NONE",
                   "currencyCode": None, "minValue": None, "maxValue": None},
                  {"id": "s", "summary": "$90K – $120K", "compensationType": "Salary", "interval": "1 YEAR",
                   "currencyCode": "USD", "minValue": 90000, "maxValue": 120000}]}]}},
             {"id": "j2", "title": "Hidden role", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/ramp/j2",
              "location": "Remote"}],
}

WORKABLE = {"name": "Seeq", "description": "", "jobs": [
    {"title": "AI Software Engineer - Staff/Principal", "shortcode": "1B6E", "code": "2026-45",
     "employment_type": "Full-time", "telecommuting": True, "department": "Software Engineering",
     "url": "https://apply.workable.com/j/1B6E", "shortlink": "https://apply.workable.com/j/1B6E",
     "application_url": "https://apply.workable.com/j/1B6E/apply", "published_on": iso(4)[:10],
     "created_at": iso(6)[:10], "country": "United States", "city": "", "state": "", "education": None,
     "experience": "Mid-Senior level", "function": "Engineering", "industry": "Computer Software",
     "locations": [{"country": "United States", "countryCode": "US", "city": None, "region": None, "hidden": False}]}]}

RECRUITEE = {"offers": [
    {"id": 1957982, "title": "Online English teacher for kids", "location": "Remote job", "city": "Kyiv",
     "country": "Ukraine", "country_code": "UA", "remote": True, "hybrid": False, "on_site": False,
     "employment_type_code": "freelance", "salary": {"max": None, "min": None, "period": None, "currency": None},
     "published_at": (NOW - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S UTC"), "experience_code": "entry_level",
     "company_name": "AllRight", "careers_url": "https://allright.recruitee.com/o/online-english-teacher",
     "description": "<p>Teach English to kids online.</p>", "requirements": "<p>Teaching experience.</p>",
     "department": "Teachers", "tags": []}]}

SMARTRECRUITERS = {"offset": 0, "limit": 50, "totalFound": 1, "content": [
    {"id": "744000156179239", "name": "Python Developer", "uuid": "u", "refNumber": "R",
     "company": {"identifier": "BoschGroup", "name": "Bosch Group"}, "releasedDate": iso(2),
     "location": {"city": "Stuttgart", "region": "BW", "country": "de", "remote": False, "hybrid": True,
                  "fullLocation": "Stuttgart, Baden-Württemberg, Germany"},
     "industry": {"id": "x", "label": "Automotive"}, "department": {}, "function": {"id": "it", "label": "IT"},
     "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
     "experienceLevel": {"id": "mid_senior_level", "label": "Mid-Senior Level"}}]}

REMOTIVE = {"00-warning": "...", "0-legal-notice": "...", "job-count": 2, "total-job-count": 2, "jobs": [
    {"id": 1, "url": "https://remotive.com/remote-jobs/software-dev/python-dev-1", "title": "Python Developer",
     "company_name": "Mitre Media", "company_logo": "x", "category": "Software Development",
     "tags": ["python", "django", "aws"], "job_type": "full_time", "publication_date": iso(2)[:19],
     "candidate_required_location": "Europe", "salary": "€70k - €90k", "description": "<p>Python, Django.</p>"},
    {"id": 2, "url": "https://remotive.com/remote-jobs/marketing/seo-2", "title": "SEO Manager",
     "company_name": "Cryptobet", "company_logo": "x", "category": "Marketing", "tags": ["seo"],
     "job_type": "full_time", "publication_date": iso(1)[:19], "candidate_required_location": "Worldwide",
     "salary": "", "description": "<p>Grow our crypto casino.</p>"}]}

REMOTEOK = [{"last_updated": ts(0), "legal": "API Terms of Service: Please link back..."},
            {"slug": "remote-backend-engineer-acme-1", "id": "1", "epoch": ts(1), "date": iso(1), "company": "Globex",
             "company_logo": "", "position": "Backend Engineer", "tags": ["python", "backend"],
             "description": "Python and PostgreSQL", "location": "Worldwide", "apply_url": "https://remoteok.com/l/1",
             "verified": True, "salary_min": 80000, "salary_max": 110000, "logo": "", "url": "https://remoteok.com/remote-jobs/1"}]

JOBICY = {"apiVersion": "2", "jobCount": 1, "jobs": [
    {"id": 155742, "url": "https://jobicy.com/jobs/155742-director", "jobSlug": "x", "jobTitle": "Director of Security Operations",
     "companyName": "EDB", "companyLogo": "", "jobIndustry": ["Cybersecurity"], "jobType": ["Full-Time"],
     "jobGeo": "USA", "jobLevel": "Director", "jobExcerpt": "Lead SOC", "jobDescription": "<p>SIEM</p>",
     "pubDate": iso(1)}]}

ARBEITNOW = {"data": [
    {"slug": "x", "company_name": "Sound People BV", "title": "Python Entwickler (m/w/d)",
     "description": "<p>Python, Django</p>", "remote": False, "url": "https://www.arbeitnow.com/jobs/x",
     "tags": ["python"], "job_types": ["fulltime permanent"], "location": "Hamburg, Germany", "created_at": ts(2)}],
    "links": {"first": "", "last": "", "prev": None, "next": None}, "meta": {}}

MUSE = {"page": 1, "page_count": 1, "items_per_page": 20, "total": 1, "results": [
    {"contents": "<p>Embedded C++ on Linux</p>", "name": "Sr. Embedded Software Engineer", "type": "external",
     "publication_date": iso(10), "short_name": "x", "model_type": "jobs", "id": 21825761,
     "locations": [{"name": "Lockhart, TX"}], "categories": [{"name": "Software Engineering"}],
     "levels": [{"name": "Senior Level", "short_name": "senior"}], "tags": [],
     "refs": {"landing_page": "https://www.themuse.com/jobs/spacex/sr-embedded"},
     "company": {"id": 1, "short_name": "spacex", "name": "SpaceX"}}]}

HIMALAYAS = {"comments": "", "offset": 0, "limit": 20, "totalCount": 1, "jobs": [
    {"title": "Senior Python Engineer", "excerpt": "", "companyName": "Wellfound Co", "companySlug": "x",
     "companyLogo": "", "employmentType": "Full Time", "minSalary": 120000, "maxSalary": 150000,
     "salaryPeriod": "annual", "seniority": ["Senior"], "currency": "USD", "locationRestrictions": ["United States"],
     "timezoneRestrictions": [-5], "categories": ["Python-Developer"], "parentCategories": [],
     "description": "<p>Python and AWS</p>", "pubDate": ts(1), "expiryDate": ts(-30),
     "applicationLink": "https://himalayas.app/companies/x/jobs/senior-python", "guid": "g"}]}

HN_STORIES = {"hits": [{"objectID": "49922569", "title": "Ask HN: Who is hiring? (October 2026)",
                        "created_at": iso(18)},
                       {"objectID": "49922568", "title": "Ask HN: Who wants to be hired? (October 2026)",
                        "created_at": iso(18)}]}
HN_COMMENTS = {"nbHits": 2, "hits": [
    {"objectID": "50001", "parent_id": 49922569, "story_id": 49922569, "created_at": iso(4),
     "comment_text": "NeuralFrame | Senior Backend Engineer (Python + Rust) | REMOTE (US only) | Full-time | "
                     "$170k–$210k<p>We build data pipelines in Python. No visa sponsorship.",
     "author": "a"},
    {"objectID": "50002", "parent_id": 50001, "story_id": 49922569, "created_at": iso(3),
     "comment_text": "Is this still open?", "author": "b"}]}

LINKEDIN_HTML = """
<li><div class="base-card base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:4477761949">
<a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/x-4477761949?trk=1"><span class="sr-only">x</span></a>
<div class="base-search-card__info"><h3 class="base-search-card__title"> (Senior) Software Developer Backend / Python </h3>
<h4 class="base-search-card__subtitle"><a href="#"> Athereon GRC GmbH </a></h4>
<div class="base-search-card__metadata"><span class="job-search-card__location"> Saarbrücken, Saarland, Germany </span>
<time class="job-search-card__listdate" datetime="2026-09-22"> 3 weeks ago </time></div></div></div></li>
"""

JOBPOSTING_HTML = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": "Initech"},
 {"@type": "JobPosting", "title": "Registered Nurse - ICU", "datePosted": "%s",
  "validThrough": "%s", "employmentType": ["FULL_TIME"],
  "hiringOrganization": {"@type": "Organization", "name": "Charité"},
  "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Berlin",
                  "addressCountry": "DE"}},
  "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR",
                 "value": {"@type": "QuantitativeValue", "minValue": 48000, "maxValue": 60000, "unitText": "YEAR"}},
  "description": "<p>Intensive care nursing. German B2 required.</p>"}]}
</script></head><body>job</body></html>""" % (iso(3)[:10], (NOW + timedelta(days=30)).date().isoformat())

EXPIRED_HTML = JOBPOSTING_HTML.replace((NOW + timedelta(days=30)).date().isoformat(), "2020-01-01")

SEARCH_RESULTS = {"results": [
    {"title": "Registered Nurse ICU - Charité", "url": "https://careers.example-hospital.de/jobs/42", "content": "ICU nurse Berlin"},
    {"title": "ICU Nurse - Vivantes - Berlin | Indeed", "url": "https://de.indeed.com/viewjob?jk=abc", "content": "Berlin"},
    {"title": "Jobs at Newco", "url": "https://job-boards.greenhouse.io/newco/jobs/5", "content": "Newco careers"},
    {"title": "Nurse forum", "url": "https://www.reddit.com/r/nursing/1", "content": ""}]}

NEWCO_GREENHOUSE = {"jobs": [
    {"absolute_url": "https://job-boards.greenhouse.io/newco/jobs/5", "location": {"name": "Berlin, Germany"},
     "id": 5, "updated_at": iso(1), "title": "ICU Nurse", "company_name": "Newco", "first_published": iso(1),
     "content": "&lt;p&gt;Nursing in Berlin&lt;/p&gt;", "metadata": [], "departments": [], "offices": []}]}
