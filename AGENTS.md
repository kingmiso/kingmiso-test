# KingMiso — persistent project requirements

- All work is iPhone-first regardless of whether the user works on iPad or desktop.
- Design and verify widths 360, 393 and 430 CSS pixels; include a short 580px viewport to account for mobile browser chrome.
- iPad and desktop use the same portrait art, landmark positions and controls in a centered max-width 430px game shell. Never select a different square map by device width.
- Preserve the existing royal blue/gold fantasy anime art style.
- Building detail has a scrollable information body and a permanently visible action footer; map fills shell width and can scroll/pan vertically.
- Chat sits below bottom navigation, shows only the latest two messages, and opens a dedicated page for full available server history and composition.
- Keep gameplay progression, save compatibility and economy intact. UI assets and layout must remain separate from balance configuration and economic logic.
- Verify construction start/progress/completion once, hero unlocks, chat navigation and tab switching.
- Never claim a live GitHub deployment unless it has actually been deployed.

- Distribute deployment files in a flat ZIP, without nested asset folders, for iPhone GitHub uploads.
- Finish the domain visual composition before proceeding to further changes in other game sections. Domain HUD and bottom navigation should overlay the map as one continuous game scene.

- v2.0.41 authorized production change: each completed facility upgrade adds its pre-upgrade level plus castle level captured when construction starts to its base output per second. Old saves retain their current output; future increases persist in productionV241.
- Durations use Dd HH:MM:SS. Map touch feedback must preserve translate(-50%,-50%) anchors.

- v2.0.42: omit the day prefix for durations below one day; show larger level/nickname/power without the domain title in the HUD. Active building/gathering/hero jobs can be cancelled with exactly 50% of paid resources refunded once. New jobs persist paidCostsV242; legacy jobs infer unchanged pre-upgrade costs.

- v2.0.43: HUD level, nickname and power share one line. Domain/gather detail uses saved-job progress for workshop animation; honor reduced motion and keep action footer visible.

- v2.0.47: timed building, gathering and hero upgrades accelerate by 720 seconds per diamond; never charge completed jobs. Original job resources refund 50% on cancellation; acceleration diamonds are consumed. Gathering uses four compact illustrated cards with working controls.

- v2.0.48 master style: fine gold borders, warm cream type, honey-gold buttons; flat periwinkle navigation silhouettes (house, pickaxe, cute face, crossed swords, shop). Avoid metallic bevels, bulky tile selection and oversized icons.

- v2.0.49 supersedes thin borders: rounded cute colored navigation, substantial 2px UI outlines, roomy diamond capsule, no map zoom controls. Warm storybook gathering art in list and details.

- v2.0.50: domain art matches gathering storybook style with landmark anchors preserved. Fantasy navigation uses crown castle, crystal pickaxe, mage, rune swords and treasure chest.
