"""TF-IDF + K-means analysis for research directions and keyword trends."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

if TYPE_CHECKING:
    from src.storage import PaperStore


CONFERENCES = ("CVPR", "ICCV", "ECCV")
GENERIC_TERMS = set(ENGLISH_STOP_WORDS) | {"survey", "surveys", "review", "reviews", "comprehensive", "systematic", "overview", "paper", "papers", "model", "models", "method", "methods", "approach", "approaches"}
ANALYSIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS topic_clusters (
    cluster_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    paper_count INTEGER NOT NULL,
    score REAL NOT NULL,
    terms_json TEXT NOT NULL,
    run_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_analysis (
    paper_id INTEGER PRIMARY KEY,
    cluster_id INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keyword_stats (
    keyword TEXT PRIMARY KEY,
    paper_count INTEGER NOT NULL,
    weight REAL NOT NULL,
    rank INTEGER NOT NULL,
    run_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keyword_papers (
    keyword TEXT NOT NULL,
    paper_id INTEGER NOT NULL,
    PRIMARY KEY (keyword, paper_id)
);
CREATE TABLE IF NOT EXISTS trend_stats (
    keyword TEXT NOT NULL,
    venue TEXT NOT NULL,
    year INTEGER NOT NULL,
    paper_count INTEGER NOT NULL,
    PRIMARY KEY (keyword, venue, year)
);
CREATE TABLE IF NOT EXISTS analysis_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class AnalysisEngine:
    """Rebuild derived analytics after papers are added or updated."""

    def __init__(self, store: "PaperStore"):
        self.store = store

    def refresh(self) -> dict:
        rows = self.store.all(limit=100000)
        run_at = datetime.now(timezone.utc).isoformat()
        with self.store.connection() as connection:
            connection.executescript(ANALYSIS_SCHEMA)
            for table in (
                "topic_clusters",
                "paper_analysis",
                "keyword_stats",
                "keyword_papers",
                "trend_stats",
            ):
                connection.execute(f"DELETE FROM {table}")

            if not rows:
                self._write_meta(connection, run_at, 0, 0)
                connection.commit()
                return self.summary()

            documents = [self._document(row) for row in rows]
            vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words=list(GENERIC_TERMS),
                ngram_range=(1, 2),
                min_df=1,
                max_features=4000,
                token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9-]{2,}\b",
            )
            matrix = vectorizer.fit_transform(documents)
            terms = vectorizer.get_feature_names_out()
            cluster_count = self._cluster_count(len(rows))
            if cluster_count == 1:
                labels = [0] * len(rows)
                centers = matrix.mean(axis=0).A1
            else:
                model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
                labels = model.fit_predict(matrix).tolist()
                centers = model.cluster_centers_

            self._write_clusters(connection, labels, centers, terms, run_at)
            self._write_vectors(connection, rows, labels, matrix, terms, run_at)
            self._write_keywords(connection, rows, matrix, terms, run_at)
            self._write_trends(connection, rows, matrix, terms)
            self._write_meta(connection, run_at, len(rows), cluster_count)
            connection.commit()
        return self.summary()

    def summary(self, limit: int = 10) -> dict:
        with self.store.connection() as connection:
            topics = []
            for row in connection.execute(
                "SELECT * FROM topic_clusters ORDER BY paper_count DESC, score DESC LIMIT ?",
                (limit,),
            ):
                item = dict(row)
                item["terms"] = json.loads(item.pop("terms_json"))
                topics.append(item)
            keywords = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM keyword_stats ORDER BY rank LIMIT ?", (limit,)
                )
            ]
            meta = dict(connection.execute("SELECT key, value FROM analysis_meta").fetchall())
            return {
                "paper_count": int(meta.get("paper_count", 0)),
                "cluster_count": int(meta.get("cluster_count", 0)),
                "run_at": meta.get("run_at"),
                "topics": topics,
                "keywords": keywords,
            }

    def papers_for_keyword(self, keyword: str, limit: int = 50) -> list[dict]:
        with self.store.connection() as connection:
            rows = connection.execute(
                """
                SELECT p.* FROM keyword_papers kp
                JOIN papers p ON p.id = kp.paper_id
                WHERE kp.keyword = ?
                ORDER BY p.year DESC, p.title ASC LIMIT ?
                """,
                (keyword.casefold().strip(), limit),
            )
            return [self.store._row_to_dict(row) for row in rows]

    def trends(self, keywords: Iterable[str] | None = None) -> dict:
        with self.store.connection() as connection:
            params: tuple = ()
            where = ""
            selected = [k.casefold().strip() for k in keywords or [] if k.strip()]
            if selected:
                marks = ",".join("?" for _ in selected)
                where = f"WHERE keyword IN ({marks})"
                params = tuple(selected)
            rows = connection.execute(
                f"SELECT keyword, venue, year, paper_count FROM trend_stats {where} ORDER BY year, venue, keyword",
                params,
            )
            records = [dict(row) for row in rows]
        years = sorted({row["year"] for row in records})
        venues = [venue for venue in CONFERENCES if any(row["venue"] == venue for row in records)]
        return {"years": years, "venues": venues, "records": records}

    @staticmethod
    def _document(row: dict) -> str:
        keywords = row.get("keywords") or []
        return " ".join(
            part
            for part in (row.get("title"), row.get("abstract"), " ".join(keywords))
            if part
        )

    @staticmethod
    def _cluster_count(paper_count: int) -> int:
        if paper_count <= 1:
            return 1
        return min(10, max(2, round(math.sqrt(paper_count))))

    @staticmethod
    def _top_terms(values, terms, limit: int = 5) -> list[str]:
        order = sorted(range(len(values)), key=lambda index: float(values[index]), reverse=True)
        return [str(terms[index]) for index in order[:limit] if float(values[index]) > 0]

    def _write_clusters(self, connection, labels, centers, terms, run_at: str) -> None:
        counts = Counter(labels)
        for cluster_id, count in counts.items():
            center = centers if len(counts) == 1 else centers[cluster_id]
            top_terms = self._top_terms(center, terms)
            label = " / ".join(term.title() for term in top_terms) or f"方向 {cluster_id + 1}"
            score = float(sum(float(value) for value in center))
            connection.execute(
                "INSERT INTO topic_clusters VALUES (?, ?, ?, ?, ?, ?)",
                (cluster_id, label, count, score, json.dumps(top_terms), run_at),
            )

    def _write_vectors(self, connection, rows, labels, matrix, terms, run_at: str) -> None:
        for row_index, row in enumerate(rows):
            values = matrix.getrow(row_index)
            vector = {
                str(terms[index]): round(float(value), 6)
                for index, value in zip(values.indices, values.data)
                if value > 0
            }
            top_vector = dict(sorted(vector.items(), key=lambda item: item[1], reverse=True)[:60])
            connection.execute(
                "INSERT INTO paper_analysis VALUES (?, ?, ?, ?)",
                (row["id"], int(labels[row_index]), json.dumps(top_vector), run_at),
            )

    def _write_keywords(self, connection, rows, matrix, terms, run_at: str) -> None:
        document_frequency = (matrix > 0).sum(axis=0).A1
        total_weight = matrix.sum(axis=0).A1
        ranking = sorted(
            range(len(terms)),
            key=lambda index: (float(document_frequency[index]), float(total_weight[index])),
            reverse=True,
        )
        selected = ranking[:80]
        for rank, term_index in enumerate(selected, start=1):
            keyword = str(terms[term_index])
            connection.execute(
                "INSERT INTO keyword_stats VALUES (?, ?, ?, ?, ?)",
                (
                    keyword,
                    int(document_frequency[term_index]),
                    round(float(total_weight[term_index]), 6),
                    rank,
                    run_at,
                ),
            )
            for paper_index in matrix[:, term_index].nonzero()[0].tolist():
                connection.execute(
                    "INSERT INTO keyword_papers VALUES (?, ?)",
                    (keyword, rows[paper_index]["id"]),
                )

    def _write_trends(self, connection, rows, matrix, terms) -> None:
        index_by_term = {str(term): index for index, term in enumerate(terms)}
        stats = defaultdict(int)
        for row_index, row in enumerate(rows):
            venue = str(row.get("venue") or "").upper()
            year = row.get("year")
            if venue not in CONFERENCES or not year or row.get("paper_type") == "user-import":
                continue
            present = matrix.getrow(row_index).indices
            for term_index in present:
                keyword = str(terms[term_index])
                if keyword in index_by_term:
                    stats[(keyword, venue, int(year))] += 1
        connection.executemany(
            "INSERT INTO trend_stats VALUES (?, ?, ?, ?)",
            [(keyword, venue, year, count) for (keyword, venue, year), count in stats.items()],
        )

    @staticmethod
    def _write_meta(connection, run_at: str, paper_count: int, cluster_count: int) -> None:
        connection.executemany(
            "INSERT OR REPLACE INTO analysis_meta(key, value) VALUES (?, ?)",
            [
                ("run_at", run_at),
                ("paper_count", str(paper_count)),
                ("cluster_count", str(cluster_count)),
                ("vectorizer", "tfidf"),
                ("clusterer", "kmeans"),
            ],
        )
