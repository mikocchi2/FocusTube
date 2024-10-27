from openai import OpenAI
client = OpenAI(api_key='sk-proj-JA6oGfpgDSiVs0IrKy5QT3BlbkFJJfGXjiQUn2hl4aPcbOJH')


def askGpt(prompt):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": f"{prompt}"
            }
        ]
    )

    #print(completion.choices[0].message.content)
    return completion.choices[0].message.content