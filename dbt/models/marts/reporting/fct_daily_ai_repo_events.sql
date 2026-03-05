{{
  config(
    materialized='incremental',
    unique_key=['event_date', 'repo_name', 'event_type'],
    incremental_strategy='merge',
    on_schema_change='append_new_columns'  )
}}

select
    date(created_at) as event_date,
    repo_name,
    event_type,
    count(distinct event_id) as event_count,
    count(distinct actor_login) as unique_actors
from {{ ref('fct_ai_repo_events') }}

{% if is_incremental() %}
where date(created_at) > (select max(event_date) from {{ this }})
{% endif %}

group by event_date, repo_name, event_type