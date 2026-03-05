with ai_repos as (

    select repo_name from {{ ref('int_ai_repo_names') }}

)

select distinct repo_name from ai_repos
