# Urumi dashboard: refined product direction

Design review artifact, not the deployed gateway. The user rejected the prior previews and requested the visual quality of established consumer products: coherent identity, attractive text, modular icons, favicon and thoughtfully composed screens.

## Direction

An approachable white workspace with a restrained coral accent, strong charcoal text and Figtree typography. The task owns the visual focus: the composer in the start view, the answer in the result view, and readable server/tool information in the server view. Shared spacing, controls, icon sizes and type weights connect the screens. Avoid oversized marketing headings, repeated cards around every paragraph and faint small text.

This prototype explores presentation only. It uses sample data and does not send chat, make tool calls or change accounts. The production identity, roles, gateway routing, audit requirements, independent-message behavior and security constraints remain governed by the M8 amendment and project instructions. The application design still requires user review before implementation.

## References and local assets

- Primary dashboard composition reference: [Chatbot UI Web App Design, Ronas IT](https://dribbble.com/shots/26499906-Chatbot-UI-Web-App-Design). Borrow the conversation-first hierarchy, clear navigation and restrained accent; adapt the layout to Urumi's actual functions. No billing, model picker, attachments or saved-history feature is proposed.
- Secondary workspace reference: [Omni Agent, LAIN Design Agency](https://dribbble.com/shots/26427853-Omni-Agent-Smart-AI-Copilot-Assistant-Dashboard-UI-UX-Design). Reference for the uncluttered composer and prompt-card treatment.
- Typography rationale: [Crafting the Airbnb Cereal Typeface, Karri Saarinen](https://karrisaarinen.com/posts/developing-airbnb-cereal/). Our design uses Figtree, not Airbnb's custom font or branding.
- [Figtree from Google Fonts](https://github.com/google/fonts/tree/main/ofl/figtree), stored locally. License: [SIL Open Font License](assets/Figtree-OFL.txt).
- [Phosphor icons](https://github.com/phosphor-icons/core), one consistent regular-weight icon family stored locally. License: [MIT](assets/Phosphor-LICENSE.txt).

Downloaded reference images were removed during the user-requested cleanup on 23 October 2026; their source links remain above. No repository source or credentials were uploaded to an external design service. This retained preview records the chosen original coral direction; the implemented dashboard uses teal/light green and its own assets under `frontend/src/assets`.
