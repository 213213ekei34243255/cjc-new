"""Site page map: the old "open <page>" commands, plus keyword -> link buttons shown under answers."""

import re

CJ = "https://christjuniorcollege.in/"

# key phrase -> (label, url). Matching is "every word of the key appears in the request".
PAGES = {
    "institution": ("Open Institution", CJ + "about-the-institution.php"),
    "emblem": ("Open Emblem", CJ + "about-the-emblem.php"),
    "campus culture": ("Open Campus Culture", CJ + "about-campus-culture.php"),
    "founder": ("Open Founder", CJ + "about-founder.php"),
    "vision mission": ("Open Vision & Mission", CJ + "about-vision-mission.php"),
    "principal": ("Open Principal's Message", CJ + "about-principals-message.php"),
    "cmi": ("Open CMI Education Policy", CJ + "about-cmi-and-cmi-education-policy.php"),
    "campus": ("Open Campus", CJ + "about-campus.php"),
    "college profile": ("Open College Profile", CJ + "about-college-profile.php"),
    "academic growth": ("Open Academic Growth", CJ + "about-academic-growth.php"),
    "educational policies": ("Open Evolution of Educational Policies", CJ + "about-evolution-of-educational-policies.php"),
    "student development": ("Open Student Development", CJ + "about-student-development.php"),
    "expansion": ("Open Expansion", CJ + "about-expansion.php"),
    "infrastructure": ("Open Infrastructure", CJ + "about-infrastructure.php"),
    "pu academics": ("Open PU Academics", CJ + "academics.php"),
    "faculty": ("Open Faculty", CJ + "faculty.php"),
    "pu programs": ("Open PU Programs", CJ + "pre-university-course.php#academic-programs"),
    "pu admission": ("Open PU Admission", "https://kp.christjuniorcollege.in/CJC/cjcUniqueIdRegistration.do?method=initOnlineApplicationRegistration&pt=1"),
    "enquiry pu": ("Open PU Admission Enquiry", CJ + "admission-enquiry-pu.php"),
    "pu faqs": ("Open PU FAQs", CJ + "faqs-pu.php"),
    "student life": ("Open Student Life", CJ + "student-life.php"),
    "achievers": ("Open Achievers", CJ + "achievers.php"),
    "pu blog": ("Open PU Blog", "https://christjuniorcollege.wordpress.com/"),
    "ibdp blog": ("Open IBDP Blog", "https://cjcibdp.wordpress.com/"),
    "contact pu": ("Open PU Contact", CJ + "contact-us-pu.php"),
    "contact ibdp": ("Open IBDP Contact", CJ + "contact-us-ibdp.php"),
    "about ibdp": ("Open IBDP About", CJ + "about-us-ibdp.php"),
    "ibdp programs": ("Open IBDP Programs", CJ + "academics-programs-ibdp.php"),
    "admission ibdp": ("Open IBDP Admission Enquiry", CJ + "admission-enquiry-ibdp.php"),
    "ibdp process": ("Open IBDP Admissions Process", CJ + "admissions-process-ibdp.php"),
    "ibdp faqs": ("Open IBDP FAQs", CJ + "admission-faqs-ibdp.php"),
    "publications": ("Open IBDP Publications", CJ + "publications.php"),
    "managebac": ("Open ManageBac Login", "https://cjc.managebac.com/login"),
}

# loose topic -> pages worth offering under an answer
TOPIC_LINKS = [
    (re.compile(r"\b(admission|apply|application|enrol|register)\w*", re.I),
     [("PU admission enquiry", PAGES["enquiry pu"][1]), ("IBDP admission enquiry", PAGES["admission ibdp"][1])]),
    (re.compile(r"\bibdp?\b|\bib\b|diploma programme", re.I),
     [("About IBDP", PAGES["about ibdp"][1]), ("IBDP admissions process", PAGES["ibdp process"][1])]),
    (re.compile(r"\b(fee|fees|cost|tuition)\b", re.I), [("PU FAQs", PAGES["pu faqs"][1])]),
    (re.compile(r"\b(faculty|teacher|teachers|staff)\b", re.I), [("Faculty", PAGES["faculty"][1])]),
    (re.compile(r"\b(club|clubs|event|events|fest|sports|student life)\b", re.I), [("Student life", PAGES["student life"][1])]),
    (re.compile(r"\b(campus|infrastructure|facilit\w+|library|lab|labs)\b", re.I),
     [("Campus", PAGES["campus"][1]), ("Infrastructure", PAGES["infrastructure"][1])]),
    (re.compile(r"\b(contact|phone|call|email|address|location|reach)\b", re.I),
     [("Contact (PU)", PAGES["contact pu"][1]), ("Contact (IBDP)", PAGES["contact ibdp"][1])]),
]


def match_page(query):
    """Resolve the text after the word 'open' to one of PAGES, or None."""
    q = (query or "").lower().strip()
    for key, (label, url) in PAGES.items():
        if all(word in q for word in key.split()):
            return label, url
    return None


def suggest_links(text, limit=2):
    out = []
    for pattern, links in TOPIC_LINKS:
        if pattern.search(text or ""):
            for label, url in links:
                if (label, url) not in out:
                    out.append((label, url))
    return [{"label": l, "url": u} for l, u in out[:limit]]
