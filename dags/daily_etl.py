"""Airflow DAG — daily Barcelona real estate extraction.

STUB. Wire this into an Airflow deployment once the scrapers are stable.
Each provider is its own task so one failing source does not block the others.
The Spark transformation task is a placeholder for the Scala job (Phase: transformation).
"""

from __future__ import annotations

from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:  # Airflow not installed in the scraping venv — stub stays importable
    DAG = None  # type: ignore[assignment,misc]
    PythonOperator = None  # type: ignore[assignment,misc]


def _scrape(provider_name: str) -> None:
    from etl.run_all import PROVIDERS, run_provider

    run_provider(provider_name, PROVIDERS[provider_name])


default_args = {
    "owner": "barcelona-real-state",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def build_dag() -> "DAG":
    with DAG(
        dag_id="daily_real_estate_etl",
        description="Daily scrape of habitaclia, idealista, fotocasa → Postgres",
        schedule="@daily",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        default_args=default_args,
        tags=["etl", "scraping", "barcelona"],
    ) as dag:
        scrape_tasks = [
            PythonOperator(
                task_id=f"scrape_{name}",
                python_callable=_scrape,
                op_args=[name],
            )
            for name in ("habitaclia", "idealista", "fotocasa")
        ]

        transform = PythonOperator(
            task_id="spark_transform",
            python_callable=lambda: print("TODO: trigger Scala Spark transformation job"),
        )

        scrape_tasks >> transform  # type: ignore[operator]
    return dag


if DAG is not None:
    dag = build_dag()
