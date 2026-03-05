with star_events as (

    select * from {{ ref('int_star_events') }}

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
from star_events e
inner join ai_repo_names r
    on e.repo_name = r.repo_name
