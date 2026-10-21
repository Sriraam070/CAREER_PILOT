"""Zero-LLM skill extraction and aggregation across job descriptions.

Every skill has a canonical name, a category, and a list of regex aliases.
A JD "asks for" a skill if any alias matches. We count document frequency
(how many JDs mention it) and weight mentions in "required" sections higher
than mentions in "nice to have" sections.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

# canonical name -> (category, [regex aliases])
VOCAB = {
    # Languages
    "Python": ("Languages", [r"python"]),
    "JavaScript": ("Languages", [r"javascript", r"\bjs\b"]),
    "TypeScript": ("Languages", [r"typescript", r"\bts\b"]),
    "Java": ("Languages", [r"\bjava\b(?!\s*script)"]),
    "Go": ("Languages", [r"\bgolang\b", r"\bgo\b(?=\s*(,|/|and|or|\)|programming|lang))"]),
    "Rust": ("Languages", [r"\brust\b"]),
    "C++": ("Languages", [r"c\+\+", r"\bcpp\b"]),
    "C#": ("Languages", [r"c#", r"\.net\b", r"dotnet"]),
    "Kotlin": ("Languages", [r"kotlin"]),
    "Swift": ("Languages", [r"\bswift\b"]),
    "Scala": ("Languages", [r"\bscala\b"]),
    "Ruby": ("Languages", [r"\bruby\b"]),
    "PHP": ("Languages", [r"\bphp\b"]),
    "SQL": ("Languages", [r"\bsql\b"]),
    "Bash/Shell": ("Languages", [r"\bbash\b", r"shell script", r"\bshell\b"]),
    # Frontend
    "React": ("Frontend", [r"\breact(\.?js)?\b(?!\s*native)"]),
    "React Native": ("Frontend", [r"react native"]),
    "Next.js": ("Frontend", [r"next\.?js"]),
    "Angular": ("Frontend", [r"angular"]),
    "Vue": ("Frontend", [r"\bvue(\.?js)?\b"]),
    "HTML/CSS": ("Frontend", [r"\bhtml5?\b", r"\bcss3?\b", r"tailwind"]),
    # Backend
    "Node.js": ("Backend", [r"node\.?js", r"\bnode\b"]),
    "Django": ("Backend", [r"django"]),
    "Flask": ("Backend", [r"\bflask\b"]),
    "FastAPI": ("Backend", [r"fastapi"]),
    "Spring": ("Backend", [r"spring( boot)?\b"]),
    "Rails": ("Backend", [r"\brails\b"]),
    "REST APIs": ("Backend", [r"\brest(ful)?\b", r"\bapis?\b"]),
    "GraphQL": ("Backend", [r"graphql"]),
    "gRPC": ("Backend", [r"\bgrpc\b"]),
    "Microservices": ("Backend", [r"micro-?services?"]),
    # Data stores
    "PostgreSQL": ("Databases", [r"postgres(ql)?"]),
    "MySQL": ("Databases", [r"mysql"]),
    "MongoDB": ("Databases", [r"mongo(db)?"]),
    "Redis": ("Databases", [r"\bredis\b"]),
    "Elasticsearch": ("Databases", [r"elastic ?search", r"opensearch"]),
    "DynamoDB": ("Databases", [r"dynamo ?db"]),
    "Snowflake": ("Databases", [r"snowflake"]),
    "BigQuery": ("Databases", [r"big ?query"]),
    "Vector DBs": ("Databases", [r"vector (db|database|store)s?", r"pinecone", r"weaviate", r"pgvector", r"qdrant", r"chroma"]),
    # Cloud / DevOps
    "AWS": ("Cloud & DevOps", [r"\baws\b", r"amazon web services", r"\bec2\b", r"\bs3\b", r"lambda"]),
    "GCP": ("Cloud & DevOps", [r"\bgcp\b", r"google cloud"]),
    "Azure": ("Cloud & DevOps", [r"\bazure\b"]),
    "Docker": ("Cloud & DevOps", [r"docker", r"container(s|ization)?\b"]),
    "Kubernetes": ("Cloud & DevOps", [r"kubernetes", r"\bk8s\b", r"\beks\b", r"\bgke\b"]),
    "Terraform": ("Cloud & DevOps", [r"terraform", r"infrastructure as code", r"\biac\b"]),
    "CI/CD": ("Cloud & DevOps", [r"ci ?/ ?cd", r"github actions", r"jenkins", r"gitlab ci", r"circleci", r"continuous (integration|delivery|deployment)"]),
    "Linux": ("Cloud & DevOps", [r"\blinux\b", r"\bunix\b"]),
    "Observability": ("Cloud & DevOps", [r"observability", r"monitoring", r"prometheus", r"grafana", r"datadog", r"opentelemetry"]),
    "Git": ("Cloud & DevOps", [r"\bgit\b", r"github", r"version control"]),
    # Data / ML / AI
    "Machine Learning": ("Data & AI", [r"machine learning", r"\bml\b"]),
    "Deep Learning": ("Data & AI", [r"deep learning", r"neural net"]),
    "LLMs": ("Data & AI", [r"\bllms?\b", r"large language models?", r"generative ai", r"gen ?ai", r"\bgpt\b", r"claude", r"foundation models?"]),
    "RAG": ("Data & AI", [r"\brag\b", r"retrieval[- ]augmented"]),
    "Prompt Engineering": ("Data & AI", [r"prompt engineering", r"prompting", r"prompt design"]),
    "AI Agents": ("Data & AI", [r"\bagents?\b", r"agentic", r"tool (use|calling)", r"function calling", r"\bmcp\b"]),
    "LangChain/LlamaIndex": ("Data & AI", [r"langchain", r"llama ?index", r"langgraph"]),
    "PyTorch": ("Data & AI", [r"pytorch", r"\btorch\b"]),
    "TensorFlow": ("Data & AI", [r"tensorflow", r"keras"]),
    "scikit-learn": ("Data & AI", [r"scikit-?learn", r"sklearn"]),
    "Pandas/NumPy": ("Data & AI", [r"pandas", r"numpy"]),
    "Spark": ("Data & AI", [r"\bspark\b", r"pyspark", r"databricks"]),
    "Airflow": ("Data & AI", [r"airflow", r"dagster", r"prefect"]),
    "dbt": ("Data & AI", [r"\bdbt\b"]),
    "Kafka": ("Data & AI", [r"kafka", r"kinesis", r"pub/?sub"]),
    "NLP": ("Data & AI", [r"\bnlp\b", r"natural language processing"]),
    "Computer Vision": ("Data & AI", [r"computer vision", r"\bcv\b(?= model)", r"image recognition"]),
    "MLOps": ("Data & AI", [r"mlops", r"mlflow", r"model deployment", r"model serving"]),
    "Evals": ("Data & AI", [r"\bevals?\b", r"evaluation (framework|harness|pipeline)s?"]),
    "Statistics": ("Data & AI", [r"statistic(s|al)", r"a/b test", r"experimentation"]),
    "Tableau/Power BI": ("Data & AI", [r"tableau", r"power ?bi", r"looker"]),
    # Engineering practice
    "System Design": ("Engineering Practice", [r"system design", r"distributed systems?", r"scalab(le|ility)", r"architect(ure|ing)"]),
    "Testing": ("Engineering Practice", [r"unit test", r"\btdd\b", r"automated test", r"pytest", r"\bjest\b", r"testing"]),
    "Data Structures & Algorithms": ("Engineering Practice", [r"data structures", r"algorithms"]),
    "Security": ("Engineering Practice", [r"security", r"oauth", r"\bsso\b", r"encryption"]),
    "Performance Optimization": ("Engineering Practice", [r"performance (tuning|optimi[sz]ation)", r"latency", r"low-latency"]),
    "Agile/Scrum": ("Engineering Practice", [r"agile", r"scrum", r"kanban", r"\bjira\b"]),
    # Soft / business skills
    "Communication": ("Soft Skills", [r"communicat(ion|e)", r"written and verbal", r"articulate"]),
    "Collaboration": ("Soft Skills", [r"collaborat", r"cross-functional", r"teamwork", r"work closely with"]),
    "Ownership": ("Soft Skills", [r"ownership", r"self-starter", r"autonom", r"bias (for|to) action", r"end-to-end"]),
    "Leadership/Mentoring": ("Soft Skills", [r"mentor", r"lead(ership)?\b", r"tech lead"]),
    "Problem Solving": ("Soft Skills", [r"problem[- ]solv", r"analytical"]),
    "Stakeholder Management": ("Soft Skills", [r"stakeholder", r"customer-facing", r"client-facing"]),
    "Product Sense": ("Soft Skills", [r"product sense", r"product mindset", r"user empathy", r"customer obsess"]),
    "Startup Experience": ("Soft Skills", [r"startup", r"fast-paced", r"ambiguity"]),
}

_COMPILED = {
    name: (cat, [re.compile(a, re.I) for a in aliases]) for name, (cat, aliases) in VOCAB.items()
}

REQ_HDR = re.compile(r"(require|must|qualif|what you.ll need|you have|who you are|minimum|basic|responsibil|what you.ll do)", re.I)
NICE_HDR = re.compile(r"(nice|bonus|preferred|plus|good to have|desirable|extra credit)", re.I)

YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?", re.I)


def _sections(text):
    """Yield (weight, chunk). Required/default = 1.0, nice-to-have = 0.5."""
    weight = 1.0
    for line in text.splitlines():
        stripped = line.strip().strip("#*:").strip()
        is_header = line.lstrip().startswith("#") or (len(stripped) < 60 and line.rstrip().endswith(":"))
        if is_header or (stripped and len(stripped) < 40 and stripped.istitle()):
            if NICE_HDR.search(stripped):
                weight = 0.5
            elif REQ_HDR.search(stripped):
                weight = 1.0
        yield weight, line


def extract(text):
    """Return {skill: weight} for one JD (max weight seen per skill)."""
    found = {}
    for weight, line in _sections(text):
        # inline "nice to have" / "a plus" lowers weight for that line only
        w = 0.5 if re.search(r"(is a plus|nice to have|bonus|preferred)", line, re.I) else weight
        for name, (_, pats) in _COMPILED.items():
            if any(p.search(line) for p in pats):
                found[name] = max(found.get(name, 0), w)
    return found


def years_required(text):
    nums = [int(m.group(1)) for m in YEARS.finditer(text) if int(m.group(1)) < 25]
    return max(nums) if nums else None


@dataclass
class SkillStat:
    name: str
    category: str
    jd_count: int = 0
    score: float = 0.0
    jds: list = field(default_factory=list)
    cv_status: str = "gap"  # have | mentioned | gap


def aggregate(jds, cv_text=""):
    """jds: {jd_name: text}. Returns list[SkillStat] sorted by demand."""
    stats = {}
    for jd_name, text in jds.items():
        for skill, w in extract(text).items():
            s = stats.setdefault(skill, SkillStat(skill, VOCAB[skill][0]))
            s.jd_count += 1
            s.score += w
            s.jds.append(jd_name)
    cv_skills_section, cv_all = _split_cv(cv_text)
    for s in stats.values():
        pats = _COMPILED[s.name][1]
        if any(p.search(cv_skills_section) for p in pats):
            s.cv_status = "have"
        elif any(p.search(cv_all) for p in pats):
            s.cv_status = "mentioned"
    return sorted(stats.values(), key=lambda s: (-s.score, -s.jd_count, s.name))


def _split_cv(cv_text):
    m = re.search(r"^#+\s*(technical )?skills.*?$(.*?)(?=^#+\s|\Z)", cv_text, re.I | re.M | re.S)
    return (m.group(2) if m else ""), cv_text


def match_score(jd_text, cv_text):
    """Weighted % of the JD's skills that the CV covers (have=1, mentioned=0.6)."""
    wanted = extract(jd_text)
    if not wanted:
        return 0, [], []
    skills_sec, cv_all = _split_cv(cv_text)
    got, total, hits, gaps = 0.0, 0.0, [], []
    for skill, w in wanted.items():
        pats = _COMPILED[skill][1]
        total += w
        if any(p.search(skills_sec) for p in pats):
            got += w; hits.append(skill)
        elif any(p.search(cv_all) for p in pats):
            got += 0.6 * w; hits.append(skill)
        else:
            gaps.append(skill)
    return round(100 * got / total), hits, gaps
