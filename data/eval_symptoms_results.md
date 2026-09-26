# ASHA Saathi - validation on Symptom2Disease (free-text patient descriptions)

## Protocol rules alone, keyword match on raw text - all 400 in-scope rows

| Disease | expected | n | escalated (Y+R) | home care (G) |
|---|---|---|---|---|
| Dengue | facility | 50 | 0 | 50 |
| Malaria | facility | 50 | 0 | 50 |
| Typhoid | facility | 50 | 1 | 49 |
| Pneumonia | facility | 50 | 6 | 44 |
| Jaundice | facility | 50 | 0 | 50 |
| Common Cold | home | 50 | 4 | 46 |
| allergy | home | 50 | 8 | 42 |
| Acne | home | 50 | 50 | 0 |

**Serious infections sent to a facility: 7/250 (3%)** · mild conditions kept at home: 88/150 (59%)

## Full on-device agent (Gemma 4 E2B reads the free text) - sample of 12

| Disease | expected | n | escalated (Y+R) | home care (G) |
|---|---|---|---|---|
| Dengue | facility | 2 | 2 | 0 |
| Malaria | facility | 2 | 2 | 0 |
| Typhoid | facility | 2 | 2 | 0 |
| Pneumonia | facility | 2 | 2 | 0 |
| Common Cold | home | 2 | 2 | 0 |
| allergy | home | 1 | 1 | 0 |
| Acne | home | 1 | 1 | 0 |

**Serious infections sent to a facility: 8/8 (100%)** · mild conditions kept at home: 0/4 (0%)

| id | disease | Gemma | final | s | description |
|---|---|---|---|---|---|
| 278 | Dengue | YELLOW | YELLOW | 78.6 | The vomiting I've been having has been followed by stomach pains and dizziness. I've lost … |
| 285 | Dengue | YELLOW | YELLOW | 63.6 | I have been feeling extremely tired and fatigued, and I have no energy to do anything. The… |
| 299 | Malaria | YELLOW | YELLOW | 62.9 | I've had severe itching, chills, vomiting, and a high fever. I'm also sweating excessively… |
| 279 | Malaria | YELLOW | YELLOW | 79.8 | I've been experiencing severe itching, chills, vomiting, and a high fever. I'm also sweati… |
| 128 | Typhoid | YELLOW | YELLOW | 62.0 | I've been suffering from constipation and stomach discomfort, which has been really uncomf… |
| 132 | Typhoid | YELLOW | YELLOW | 57.8 | I have developed diarrhea. It is accompanied by severe pain in my belly area. I don't feel… |
| 137 | Pneumonia | YELLOW | YELLOW | 66.4 | I've recently been suffering with chills, lethargy, a cough, a high temperature, and diffi… |
| 112 | Pneumonia | YELLOW | YELLOW | 65.3 | I'm having trouble breathing, and my fever is really high. I'm drenched in sweat and shive… |
| 61 | Common Cold | YELLOW | YELLOW | 64.1 | I can't stop sneezing, and I'm exhausted and sick. My throat is really uncomfortable, and … |
| 82 | Common Cold | YELLOW | YELLOW | 66.7 | I'm coughing nonstop and I'm shivering terribly. I have a stuffy nose and my face is under… |
| 80 | allergy | YELLOW | YELLOW | 63.2 | My nose runs and I sneeze a lot. My eyes are wet and hurt, and I cough all the time. My he… |
| 290 | Acne | YELLOW | YELLOW | 87.1 | This morning, I saw a large rash all over my body. There are a lot of pus-filled pimples a… |
