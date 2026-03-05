with push_events as (

    select
        event_id,
        event_type,
        actor_login,
        repo_name,
        created_at,
        ingested_at
    from {{ ref('stg_github_event_data') }}
    where event_type = 'PushEvent'

)
select * from push_events