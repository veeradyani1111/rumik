# Prompt Log

This append-only log records user-authored prompts given to the coding agent in chronological order. Secrets, generated environment metadata, and system/developer instructions are excluded.

## 001 — 2026-08-30

> pls implement the implementation plan here, ask me for any questions.
> also we gotta store a prompt log of our conversation, how can we do that?
> it shd be fast yet tdd.

## 002 — 2026-08-30

> pls continue

## 003 — 2026-08-30

> okay

## 004 — 2026-08-30

> okay. please start the sdk and the kyc app. also put the envs in place and i will populate them with values.

## 005 — 2026-08-30

> RUMIK_GATEWAY_URL get from rumik docs please
> also why does kyc need a rumik key, livekit pipecat all those keys? it shd just need the platform key. ukwim? im so cnfused

## 006 — 2026-08-30

> yes please. thank you

## 007 — 2026-08-30

> can you now implement it?

## 008 — 2026-08-30

> nah wait, u know wait. let's keep one env file because i think I will deploy the whole folder together. jus make sure the kyc folder consumes the platform api key only.
> check the env. i have populated it. check the livekit creds

## 009 — 2026-08-30

> ok now turn both on so i can use

## 010 — 2026-08-30

> [Screenshot showing the KYC page error: "Failed to execute 'fetch' on 'Window': Illegal invocation"]

## 011 — 2026-08-30

> still this: [browser console log attached]
> plus no rumik voice came thru

## 012 — 2026-08-30

> I did test it, but I can only hear the first greeting. I cannot see myself in the
> camera, and the conversation is not happening. It should be a two way conversation,
> like an actual person doing KYC, resolving doubts, etc. See this as a whole pipeline
> and make it work correctly. Ask me for any doubts. If this needs work on the SDK,
> improve the SDK as well — look at the tools being provided and make it work. Also
> update the prompt log, and restart the local servers.

## 013 — 2026-08-30

> [browser: edge and chrome] can u also improve the UI for both of them, its v bad
> rn — nice font, positioning, colour scheme — and make them different, for obvious
> reasons: the platform UI (which hands out the key etc.) one style, and the KYC app
> a different style. Also: after the agent introduced itself I said "ok lets go" and
> never received a reply. Can you add a lot of logging everywhere to make it resilient.

## 014 — 2026-08-30

> i still spoke to it and no reply

## 015 — 2026-08-30

> it worked, the agent responded this time — but i didn't even show the PAN and it
> said a random name and PAN number, why did that happen?
> [after fix] so the SDK is now basically prompt- and tool-driven, right? how can we
> reduce the response times of the agent — the whole pipeline?

## 016 — 2026-08-30

> I saw the logs, it's around four seconds now. Any more ways to reduce latency? You
> can check the docs at Rumik (r-u-m-i-k). Also I asked if it can see — tell me my
> t-shirt colour — and it said it can't, so I'm not sure it's actually seeing
> anything. You know what I'm saying?

## 017 — 2026-08-30

> For the final verdict (verified or not) it needs something to check against — should
> we take the name (etc.) as input before the call, or say "we've noted this, we'll get
> back to you shortly"? Also, since we take the PAN card, the person's face can be a
> thing to check — how, and what do we give it to check against?
