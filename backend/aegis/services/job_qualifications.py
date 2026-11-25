"""Conservative extraction of skill evidence from job descriptions."""

import re

from aegis.schemas.matching import QualificationEvidence


SKILLS = (
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#",
    "Go", "Rust", "Ruby", "PHP", "Swift", "Kotlin",
    "Scala", "MATLAB", "SQL", "HTML", "CSS",
    "React", "Next.js", "Node.js", "Angular", "Vue.js",
    "FastAPI", "Django", "Flask", "Spring Boot", ".NET",
    "PostgreSQL", "MySQL", "SQLite", "MongoDB",
    "Redis", "Elasticsearch", "Snowflake", "BigQuery",
    "Docker", "Kubernetes", "Terraform", "Ansible",
    "Linux", "Git", "GitHub Actions", "Jenkins",
    "AWS", "Azure", "Google Cloud", "GCP",
    "REST APIs", "GraphQL", "Microservices",
    "Distributed systems", "System design",
    "Data structures", "Algorithms",
    "Apache Spark", "Apache Kafka", "Airflow",
    "Pandas", "NumPy", "PyTorch", "TensorFlow",
    "Scikit-learn", "Machine learning", "Deep learning",
    "Natural language processing", "Computer vision",
    "Generative AI", "LLMs", "MLOps",
    "Data engineering", "Data analysis",
    "Data visualization", "ETL", "Tableau", "Power BI",
    "Statistics", "A/B testing", "Excel",
    "Cybersecurity", "Network security", "OAuth",
    "Penetration testing", "Incident response",
    "Product management", "Project management",
    "Agile", "Scrum", "Stakeholder management",
    "Financial modeling", "Accounting", "Salesforce",
    "Customer success", "Technical writing",
)

REQUIRED_HEADINGS = {
    "requirements",
    "required qualifications",
    "minimum qualifications",
    "basic qualifications",
    "must have",
    "required skills",
    "what you need",
}

PREFERRED_HEADINGS = {
    "preferred qualifications",
    "preferred skills",
    "nice to have",
    "bonus points",
    "desirable qualifications",
}

OTHER_HEADINGS = {
    "responsibilities",
    "about us",
    "about the role",
    "benefits",
    "compensation",
    "salary",
    "what we offer",
    "equal opportunity",
    "what you will do",
}

OPTIONAL = re.compile(
    r"\b(?:preferred|desirable|nice to have|"
    r"bonus|a plus|optional)\b",
    re.I,
)

REQUIRED = re.compile(
    r"\b(?:required|must have|must possess|"
    r"minimum qualifications?)\b",
    re.I,
)

AMBIGUOUS = re.compile(
    r"\b(?:not required|no experience|"
    r"not necessary|not needed|not mandatory|"
    r"no prior|without experience|or|either)\b|/",
    re.I,
)

REVIEW_PATTERNS = (
    (
        r"\b\d{1,2}\s*\+?\s*(?:years?|yrs?)\b",
        "Experience duration requires manual verification.",
    ),
    (
        r"\b(?:degree|bachelor|master|phd|doctorate)\b",
        "Education requirements require manual verification.",
    ),
    (
        r"\b(?:sponsorship|visa|work authorization|"
        r"authorized to work)\b",
        "Review work authorization and sponsorship wording.",
    ),
    (
        r"\b(?:security clearance|citizenship)\b",
        "Review clearance or citizenship requirements.",
    ),
)


def extract_qualifications(
    profile, description, resume_text, normalize, contains_phrase,
):
    if len(description) > 30000 or len(resume_text) > 100000:
        raise ValueError("Qualification input exceeds limits")

    vocabulary = {}

    for skill in (*SKILLS, *profile.skills):
        key = normalize(skill)

        if key and len(key) <= 300:
            vocabulary.setdefault(key, skill)

    profile_skills = {
        normalize(skill)
        for skill in profile.skills
        if normalize(skill)
    }

    found = {}
    normalized_resume = normalize(resume_text)
    ambiguous_skills = set()
    section = "unspecified"

    for raw in description.splitlines():
        line = raw.strip().lstrip("•*- ").strip()

        if not line:
            continue

        heading = normalize(line.rstrip(":"))

        if heading in REQUIRED_HEADINGS:
            section = "required"
            continue

        if heading in PREFERRED_HEADINGS:
            section = "preferred"
            continue

        if heading in OTHER_HEADINGS:
            section = "unspecified"
            continue

        if line.endswith(":"):
            section = "unspecified"

        importance = section

        if OPTIONAL.search(line):
            importance = "preferred"
        elif REQUIRED.search(line):
            importance = "required"

        # Alternatives and negation must not become
        # independent mandatory requirements.
        if AMBIGUOUS.search(line):
            importance = "unspecified"

        normalized_line = normalize(line)

        for key, skill in vocabulary.items():
            if not contains_phrase(normalized_line, key):
                continue

            if AMBIGUOUS.search(line):
                ambiguous_skills.add(key)

            previous = found.get(key)

            if previous is not None:
                if previous[0] == importance:
                    continue

                # Conflicting classifications remain uncertain.
                if (
                    previous[0] != "unspecified"
                    and importance != "unspecified"
                ):
                    found[key] = (
                        "unspecified", previous[1],
                    )
                continue

            found[key] = (
                importance,
                line[:500],
            )

    evidence = []

    for key, (importance, excerpt) in sorted(found.items()):
        skill = vocabulary[key]

        if key in ambiguous_skills:
            importance = "unspecified"

        if key in profile_skills:
            status = "profile_match"

        elif contains_phrase(normalized_resume, key):
            status = "resume_mention"

        else:
            status = "not_evidenced"

        evidence.append(QualificationEvidence(
            skill=skill,
            importance=importance,
            status=status,
            listing_evidence=excerpt,
        ))

    return evidence[:200]


def review_items(description):
    return [
        message
        for pattern, message in REVIEW_PATTERNS
        if re.search(pattern, description, re.I)
    ]
