with events as (

    select * from {{ ref('stg_github_event_data') }}

),

ai_repo_names as (

    select repo_name from {{ ref('int_ai_repo_names') }}

)

select
    e.event_id,
    e.event_type,
    e.actor_login,
    e.repo_name,
    e.created_at,
    e.ingested_at
from events as e
inner join ai_repo_names as r
    on e.repo_name = r.repo_name
