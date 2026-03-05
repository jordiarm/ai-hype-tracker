with star_events as (

    select
        event_id,
        event_type,
        actor_login,
        repo_name,
        created_at,
        ingested_at
    from {{ ref('stg_github_event_data') }}
    where event_type = 'WatchEvent'

),

curated_repos as (

    select repo_name
    from star_events
    where repo_name in (
        'huggingface/transformers',
        'langchain-ai/langchain',
        'openai/openai-python',
        'ollama/ollama',
        'pytorch/pytorch',
        'tensorflow/tensorflow',
        'microsoft/autogen',
        'ggerganov/llama.cpp',
        'comfyanonymous/ComfyUI',
        'nomic-ai/gpt4all'
    )

),

keyword_repos as (

    select repo_name
    from star_events
    where lower(repo_name) like '%llm%'
       or lower(repo_name) like '%gpt%'
       or lower(repo_name) like '%ai%'
       or lower(repo_name) like '%ml%'
       or lower(repo_name) like '%neural%'
       or lower(repo_name) like '%diffusion%'
       or lower(repo_name) like '%langchain%'
       or lower(repo_name) like '%ollama%'
       or lower(repo_name) like '%embedding%'
       or lower(repo_name) like '%transformer%'

),

ai_repo_names as (

    select repo_name from curated_repos
    union distinct
    select repo_name from keyword_repos

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
