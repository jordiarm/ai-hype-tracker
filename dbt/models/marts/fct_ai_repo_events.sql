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
from {{ ref('int_ai_events') }}

{% if is_incremental() %}
    where created_at > coalesce(
        date_sub((select max(created_at) from {{ this }}), interval 1 day),
        timestamp('1970-01-01')
    )
{% endif %}
