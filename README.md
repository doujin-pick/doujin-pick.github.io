# 同人ピック

DLsite 公開情報ベースの同人キュレーション静的サイト（18歳以上）。

## ページ

- `index.html` — ホーム（検索・棚・最近見た）
- `explore.html` — 探す（検索＋形式／セール／価格／ソート、URL連動）
- `ranking.html` / `sale.html` / `genre.html` — 同じ探すUIのプリセット
- `about.html` — 説明・アフィ・投稿ドラフト

## フィルタ（共有URL）

例: `explore.html?q=騎士&type=game&sale=1&price=mid&sort=discount`

| パラメータ | 意味 |
|---|---|
| `q` | タイトル・サークル・タグ検索 |
| `type` | `manga_cg` / `game` / `voice` / `other` |
| `sale` | `1` でセール中のみ |
| `price` | `under1000` / `mid` / `over3000` |
| `sort` | `popular`（省略可） / `price_asc` / `discount` / `new` |
| `view` | `fav` でお気に入りのみ |
| `g` | 旧互換: `asmr` / `manga` / `game` → type に変換 |

キーボード `/` で検索フォーカス。お気に入り・最近見た・年齢確認は localStorage。

## データ更新

```bash
python3 scripts/update_works.py   # 末尾で SEO 生成も実行
python3 scripts/generate_seo_pages.py   # 単独再生成可
python3 scripts/generate_posts.py
python3 -m http.server 8765
```

SEO: `works/{id}.html`・`tags/`・`sitemap.xml`・`robots.txt`。絶対URLは `js/config.js` の `siteUrl` か環境変数 `SITE_URL`（未設定時は `https://doujin-pick.example`）。

リンク設定は `js/config.js`（dlaf.jp のみ。パラメータ自作禁止）。運営者向け。
