# ASHA Saathi - on-device image understanding probe (Gemma 4 E2B, QAT)

| Task | correct |
|---|---|
| Skin rash type (measles / chickenpox / HFMD / healthy) | 3/14 |
| Measles recognised | 0/4 |
| Anaemia pallor from eyelid photo | 3/10 |

| image | truth | Gemma | ok | s | Gemma's description |
|---|---|---|---|---|---|
| skin_measles_1.jpg | Measles | hand-foot-mouth | ❌ | 3.5 | The image shows a widespread, erythematous rash with patches of scaling or fine papules on |
| skin_measles_2.jpg | Measles | hand-foot-mouth | ❌ | 2.5 | The patient has numerous reddish, slightly raised papules and patches on the face. |
| skin_measles_3.jpg | Measles | hand-foot-mouth | ❌ | 2.5 | The skin exhibits numerous small, reddish, and slightly raised bumps across the visible ar |
| skin_measles_4.jpg | Measles | hand-foot-mouth | ❌ | 2.8 | The photo shows a widespread, erythematous rash with small, scattered papules and possibly |
| skin_chickenpox_1.jpg | Chickenpox | hand-foot-mouth | ❌ | 2.7 | The image shows multiple reddish, slightly raised bumps on the skin, which appear to be pa |
| skin_chickenpox_2.jpg | Chickenpox | hand-foot-mouth | ❌ | 2.6 | The image shows multiple red, raised, and somewhat scaly lesions on the skin. |
| skin_chickenpox_3.jpg | Chickenpox | hand-foot-mouth | ❌ | 2.9 | The image shows numerous red, raised, and somewhat inflamed lesions on the skin, suggestin |
| skin_chickenpox_4.jpg | Chickenpox | hand-foot-mouth | ❌ | 2.7 | The image shows multiple erythematous papules and some areas with scaling on the skin. |
| skin_hfmd_1.jpg | HFMD | hand-foot-mouth | ✅ | 3.5 | The patient has numerous small, raised, reddish bumps and some areas with white, scaly pat |
| skin_hfmd_2.jpg | HFMD | hand-foot-mouth | ✅ | 3.5 | The photo shows a rash on the skin with numerous small, white, raised bumps. |
| skin_hfmd_3.jpg | HFMD | hand-foot-mouth | ✅ | 3.3 | The photo shows a rash on the patient's skin with multiple red, raised, and somewhat scaly |
| skin_healthy_1.jpg | Healthy | hand-foot-mouth | ❌ | 3.0 | The image shows an area of skin with prominent, raised, reddish-brown bumps and some areas |
| skin_healthy_2.jpg | Healthy | hand-foot-mouth | ❌ | 3.2 | The image shows a patch of skin with a reddish, somewhat inflamed appearance, possibly ind |
| skin_healthy_3.jpg | Healthy | hand-foot-mouth | ❌ | 3.0 | The image shows a rash on a patient's skin characterized by small, raised, reddish bumps. |
| eye_anemia_1.jpg | Anemia | NoAnemia | ❌ | 16.4 | The conjunctiva in the image appears markedly red and inflamed, rather than pale. |
| eye_anemia_2.jpg | Anemia | Anemia | ✅ | 16.3 | The conjunctiva appears pale and somewhat congested, rather than a healthy pink-red. |
| eye_anemia_3.jpg | Anemia | Anemia | ✅ | 26.4 | The conjunctiva appears pale and somewhat dusky, rather than a healthy pink-red. |
| eye_anemia_4.jpg | Anemia | Anemia | ✅ | 23.9 | The conjunctiva appears markedly pale and somewhat dusky, suggesting pallor rather than a  |
| eye_anemia_5.jpg | Anemia | NoAnemia | ❌ | 24.5 | The lower inner eyelid (conjunctiva) shows significant redness and inflammation, appearing |
| eye_noanemia_1.jpg | NoAnemia | Anemia | ❌ | 23.1 | The conjunctiva appears distinctly pale and somewhat whitish, suggesting pallor rather tha |
| eye_noanemia_2.jpg | NoAnemia | Anemia | ❌ | 23.6 | The conjunctiva appears pale and somewhat dusky, suggesting pallor rather than a healthy p |
| eye_noanemia_3.jpg | NoAnemia | Anemia | ❌ | 25.1 | The conjunctiva in the lower inner eyelid appears markedly pale, suggesting pallor rather  |
| eye_noanemia_4.jpg | NoAnemia | Anemia | ❌ | 25.8 | The conjunctiva appears pale and somewhat dusky, suggesting pallor rather than a healthy p |
| eye_noanemia_5.jpg | NoAnemia | Anemia | ❌ | 25.2 | The lower inner eyelid (conjunctiva) appears somewhat pale with visible blood vessels, sug |
