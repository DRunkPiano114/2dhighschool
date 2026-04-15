"""Share-card rendering module.

Produces 1080x1440 PNG cards for social sharing (Xiaohongshu vertical format).
Separation of concerns:
  - elements/  : primitive visual elements (portrait, seal, balloon, etc.)
  - base.py    : BaseCardRenderer — canvas init, paper bg, font loading
  - captions.py: caption + hashtag + filename generators (pure functions)
  - assets.py  : resource paths + visual bible loader
  - cache.py   : disk cache for rendered PNGs
  - self_test.py: standalone entry for visual sanity checks
"""
