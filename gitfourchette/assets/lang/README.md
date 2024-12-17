# GitFourchette localization guide

You are welcome to submit a PR to improve an existing translation, or to localize GitFourchette to a new language!

## How to work with translation files

There are 3 kinds of translation files in `gitfourchette/assets/lang`:
- `gitfourchette.pot` is a template containing reference U.S. English text.
- `.po` files, which you can edit in [POEdit](https://poedit.net).
- `.mo` files are compiled binary files that GitFourchette reads from.

**If your language has no translation yet,** you must first create a blank `.po` file from the `.pot` template. To do that, open POEdit and go to *File » New From POT/PO File*, then select `gitfourchette/assets/lang/gitfourchette.pot`. POEdit will then ask you to pick a target language, and you can begin translating. Save the `.po` file in `gitfourchette/assets/lang` and be sure to keep the two-character language name suggested by POEdit.

**To preview your changes in GitFourchette,** generate an `.mo` file beside your `.po` file in `gitfourchette/assets/lang`. In POEdit, run *File » Compile to MO*. In GitFourchette, your new language should automatically show up in *Settings » General » Language* once you’ve generated the `.mo` file for it.

**When you’re ready to submit your translation,** commit both the `.po` file and the `.mo` file.

### Advanced/optional steps

**To sync the `.pot` and `.po` files** with any new strings from the source code **and automatically generate the `.mo` files**, you can run `./update_resources.py --lang`. Under the hood, this calls `xgettext` and `msgmerge`.

**To declutter your `.po` file,** you can clean up obsolete entries before committing. Use this command: `./update-resources.py --clean-po`

## Localization guidelines

### Git jargon

For Git-specific lingo, try to stick to [the translations that Git itself uses](https://github.com/git/git/tree/master/po). Note that this isn’t a hard rule because I’ve found that Git translations aren’t always consistent.

You can also take a look at the [“Pro Git” book](https://git-scm.com/book) in your language for extra context.

If a jargon term is of utmost importance in Git and it lacks precision in your language, consider keeping it in English, or add the English in parentheses.

For example, I translated “Push branch” to “Publier la branche (push)” in French. I consider “push” to be such an important concept in Git parlance that I want the user to know exactly which operation I’m referring to — but I’m still providing a French word so that somebody with poor English skills will still grasp what “pushing” means.

### Length variants

Occasionally, English strings contain a pipe character `|`, e.g.: `Working directory clean|Workdir clean`. For these strings, GitFourchette instructs Qt to use a shorter variant of the string if the full text doesn’t fit in its widget.

If the English string contains a pipe character, feel free to define as many variants as you like in your translation – you can add more variants than in English, or you can even just provide a single variant if your language is short enough.
