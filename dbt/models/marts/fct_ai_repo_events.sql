{{
  config(
    materialized='incremental',
    unique_key='event_id',
    incremental_strategy='merge',
    on_schema_change='append_new_columns'  )
}}

select
    event_id,
    event_type,
    actor_login,
    repo_name,
    created_at,
    ingested_at
from {{ ref('int_ai_star_events') }}

{% if is_incremental() %}
where ingested_at > (select max(ingested_at) from {{ this }})
{% endif %}