# GitFourchette localization README

You are welcome to submit a PR to improve an existing translation, or to localize the software to a new language!

## Localization guidelines

For Git-specific lingo, try to stick to [the translations that Git itself uses](https://github.com/git/git/tree/master/po). Note that this isn’t a hard rule because I’ve found that Git translations aren’t always consistent.

You can also take a look at the [“Pro Git” book](https://git-scm.com/book) in your language for extra context.

If a jargon term is of utmost importance in Git and it lacks precision in your language, consider keeping it in English, or add the English in parentheses.

For example, I translated “Push branch” to “Publier la branche (push)” in French. I consider “push” to be such an important concept in Git parlance that I want the user to know exactly which operation I’m referring to — but I’m still providing a French word so that somebody with poor English skills will still grasp what “pushing” means.

### A note about English

The source language for all localizable strings is U.S. English. However, strings containing a plural declension must still be “translated” into U.S. English.

For instance, the source code contains `Stage %n file(s)`, which `gitfourchette_en.ts` “translates” to `Stage %n file` and `Stage %n files`.

`gitfourchette_en.ts` only contains strings for singular/plural forms. This is enforced by the `-pluralonly` parameter passed to “lupdate” (in `update_resources.py`).

## How to create a new language

Let’s say you want to translate the software into Dutch (ISO-639 language code `nl`).

First, you must create a new `.ts` file for your language. The easy way is to copy an existing translation (such as `gitfourchette_fr.ts`) and change its settings in Qt Linguist. But the proper way to do it from scratch is:

```bash
pyside6-lupdate \
    -extensions py,ui \
    -source-language en \
    -target-language nl \
    -ts lang/gitfourchette_nl.ts \
    gitfourchette/
```

Then, you must let the program know about your new language:
- Add `"nl"` to the `SETTINGS` list in `gitfourchette/settings.py`

Once that’s done, read the following section for more information about updating your translation file.

## How to update an existing translation

There are two kinds of translation files:
- `.ts` files in the `lang` directory, which you can edit in [Qt Linguist](https://doc.qt.io/qt-6/linguist-translators.html).
- `.qm` files in `gitfourchette/assets` are “compiled” binary files that GitFourchette reads from.

To update an existing translation:
- Run `update_resources.py --lang` to sync the `.ts` files with any new translatable contents in the source code.
- Edit the `.ts` file for your language in [Qt Linguist](https://doc.qt.io/qt-6/linguist-translators.html).
- When you’re done editing the `.ts` file, run `update_resources.py --lang` again to update the `.qm` file.

When you‘re ready to commit your changes:
- Run `update_resources.py --clean-lang` to clean up the `.ts` files.
- Commit both the `.ts` file and the `.qm` file.

### Warning! Avoid updating .qm files while GitFourchette is running

Modifying or deleting a `.qm` file (compiled translations) that is currently loaded in GitFourchette may cause Qt to **crash!**

So, if you’re running a development copy of GitFourchette while working on the translations, you should **close it before updating the `.qm` files**.

