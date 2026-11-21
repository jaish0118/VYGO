# VYGO website

Naya blog post kaise daalein (terminal ki zaroorat nahi):

1. GitHub par repo kholo -> `posts` folder -> **Add file -> Create new file**.
2. File ka naam likho, jaise `my-first-post.md` (English letters aur `-`, space nahi).
3. Neeche wala format paste karo, heading, description, date aur video apni daal do:

```
---
title: Aapki post ki heading
description: Google me dikhne wali 1-2 line (150 akshar ke aas-paas)
date: 2026-11-22
video: https://www.youtube.com/watch?v=VIDEO_ID
---
Yahan se blog likho.

## Chhota heading

Normal text, **bold**, aur [link](https://t.me/vygoio).
```

4. **Commit changes** dabao. 1-2 minute me post blog page, home page aur sitemap.xml me apne aap aa jayegi.

- `video:` me YouTube ya Instagram reel ka link chalega. Video nahi chahiye to line hata do.
- Post chhupani ho to `draft: true` likho.
- Site Vercel par chalti hai: har commit par Vercel `python3 build.py` chalakar site banata hai (`vercel.json`).
- Domain badalne par `site.json` me `site_url` badlo.
