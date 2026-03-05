with source as (

    select * from {{ source('raw', 'raw_github_events') }}

),

cleaned as (

    select
        cast(event_id as string) as event_id,
        cast(event_type as string) as event_type,
        lower(trim(actor_login)) as actor_login,
        lower(trim(repo_name)) as repo_name,
        cast(created_at as timestamp) as created_at,
        cast(ingested_at as timestamp) as ingested_at
    from source
    where event_id is not null

)

select * from cleaned
