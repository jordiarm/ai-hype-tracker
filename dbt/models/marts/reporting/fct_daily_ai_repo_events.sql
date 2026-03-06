{{
  config(
    materialized='incremental',
    unique_key=['event_date', 'repo_name', 'event_type'],
    incremental_strategy='merge',
    on_schema_change='append_new_columns'  )
}}

select
    date(created_at) as event_date,
    extract(month from created_at) as event_month,
    extract(year from created_at) as event_year,
    repo_name,
    event_type,
    count(distinct event_id) as event_count,
    count(distinct actor_login) as unique_actors
from {{ ref('fct_ai_repo_events') }}

{% if is_incremental() %}
    where date(created_at) >= coalesce(
        date_sub((select max(event_date) from {{ this }}), interval 1 day),
        date('1970-01-01')
    )
{% endif %}

group by event_date, event_month, event_year, repo_name, event_type
