# GitFourchette localization README

You are welcome to submit a PR to improve an existing translation, or to localize the software to a new language!

## Localization guidelines

For Git-specific lingo, try to stick to the translations that Git itself uses (https://github.com/git/git/tree/master/po). Note that this isn’t a hard rule because I’ve found that Git translations aren’t always consistent.

You can also take a look at the “Pro Git” book in your language for extra context (https://git-scm.com/book).

If a jargon term is of utmost importance in Git and it lacks precision in your language, consider keeping it in English, or add the English in parentheses.

For example, I translated “Push branch” to “Publier la branche (push)” in French. I consider “push” to be such an important concept in Git parlance that I want the user to know exactly which operation I’m referring to — but I’m still providing a French word so that somebody with poor English skills will still grasp what “pushing” means.

### A note about English

The source language for all localizable strings is U.S. English. However, strings containing a plural declension must still be “translated” into U.S. English.

For instance, the source code contains `Stage %n file(s)`, which `en.ts` “translates” to `Stage %n file` and `Stage %n files`.

`en.ts` only contains strings for singular/plural forms. This is enforced by the `-pluralonly` parameter passed to “lupdate” in `update_ts.sh`.

## How to update an existing translation

- Run `lang/update_ts.sh` to sync the `.ts` files with the translatable contents of the `.py` and `.ui` files.
- Edit the `.ts` file for your language in Qt Linguist.
- Run `update_resources.py` to update the `.qm` file in `gitfourchette/assets` (**please read the warning below before running this**).
- Before committing your changes, run `lang/scrub_ts.sh` to clean up the `.ts` files.
- Commit both the `.ts` file and the `.qm` file.

### Warning: avoid updating .qm files while GitFourchette is running

Modifying or deleting a `.qm` file (compiled translations) that is currently loaded in GitFourchette may cause Qt to **crash!**

So, if you’re running a development copy of GitFourchette while working on the translations, you should **close it before updating the `.qm` files**.

## How to create a new language

Let’s say you want to translate the software into Dutch (ISO-639 language code `nl`):

- Run `pyside6-lupdate -extensions py,ui -source-language en -target-language nl gitfourchette/ -ts lang/nl.ts`
- Add an extra lupdate command for `nl` in `lang/update_ts.sh`
- Add an extra lupdate command for `nl` in `lang/scrub_ts.sh`
- Add `"nl"` to the `SETTINGS` list in `gitfourchette/settings.py`

