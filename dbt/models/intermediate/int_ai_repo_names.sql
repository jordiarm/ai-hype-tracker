with events as (
    select * from {{ ref('stg_github_event_data') }}
),

curated_repos as (

    select repo_name
    from events
    where repo_name in (
        'huggingface/transformers',
        'langchain-ai/langchain',
        'openai/openai-python',
        'ollama/ollama',
        'pytorch/pytorch',
        'tensorflow/tensorflow',
        'microsoft/autogen',
        'ggerganov/llama.cpp',
        'comfyanonymous/comfyui',
        'nomic-ai/gpt4all'
    )

),

keyword_repos as (

    select repo_name
    from events
    where
        lower(repo_name) like '%llm%'
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

select * from ai_repo_names
