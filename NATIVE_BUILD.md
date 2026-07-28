# LSD Patrol Nav — Native iOS Build Guide (Capacitor)

This wraps the existing web app in a real iOS app using **Capacitor**. Nothing about
the app has to be rewritten — Capacitor loads the same `index.html` inside a native
WebView, so everything you already use (LSD lookup, imagery download, KML lines, pins,
elevation) works the same, but as an installable app with a much larger, permanent
storage budget and no Safari data-eviction.

The app is already built to run natively: all offline data (imagery tiles, KML geometry,
pins, downloaded elevation) lives in IndexedDB / localStorage, which the native WebView
reads directly with no service worker. The survey grids, DEM, and built-in lines are
bundled with the app, so those work offline from first launch.

---

## What you need (all on a Mac)

- A **Mac** (Capacitor's iOS build only runs on macOS).
- **Xcode** — free from the Mac App Store. Open it once after installing so it finishes setup.
- **Node.js** — download the "LTS" installer from https://nodejs.org and run it.
- **CocoaPods** — in Terminal: `sudo gem install cocoapods`
- An **Apple ID**. A free one lets you run on your own iPads for 7 days at a time; a paid
  **Apple Developer account** ($99/yr) is needed to install permanently and to distribute
  to the whole fleet via TestFlight or ad-hoc.
- A USB cable to connect an iPad the first time.

---

## One-time project setup

1. Put all the app's files (everything from the repo: `index.html`, `sw.js`,
   `manifest.webmanifest`, `vendor/`, `lines/`, `ats_grid.bin`, `sk_grid.bin`,
   `dem.bin` if you built it, and the `*.png` icons) into one folder, together with the
   `package.json` and `capacitor.config.json` from this repo.

2. Open **Terminal**, and move into that folder (drag the folder onto the Terminal window
   after typing `cd ` to get the path), then run:

   ```bash
   npm install
   npm run copy:web
   npx cap add ios
   npx cap sync ios
   ```

   - `npm install` downloads Capacitor.
   - `npm run copy:web` assembles the web files into a `www/` folder (this is what gets
     bundled into the app). Re-run this any time you change the app.
   - `npx cap add ios` creates the native Xcode project (an `ios/` folder).
   - `npx cap sync ios` copies the web assets in and installs native dependencies.

3. Add the location permission so GPS works. Open
   `ios/App/App/Info.plist` in a text editor and, just before the final `</dict>`, add:

   ```xml
   <key>NSLocationWhenInUseUsageDescription</key>
   <string>Shows your aircraft position on the patrol map.</string>
   ```

---

## Build and run on an iPad

4. Open the project in Xcode:

   ```bash
   npx cap open ios
   ```

5. In Xcode:
   - In the left sidebar click the top item **App**, then the **App** target, then the
     **Signing & Capabilities** tab.
   - Check **Automatically manage signing** and pick your **Team** (your Apple ID /
     developer account). If you only have a free Apple ID, add it under
     Xcode → Settings → Accounts first.
   - Plug in the iPad. At the top of the Xcode window, choose it from the device dropdown.
   - Press the **▶ Run** button. The first time, the iPad will ask you to trust the
     developer — on the iPad go to **Settings → General → VPN & Device Management**, tap
     your developer profile, and **Trust** it, then Run again.

The app installs and launches on the iPad like any other app.

---

## First launch (do this once, online)

The grids, DEM, and built-in lines are bundled, so LSD lookup and the pipeline overview
work offline immediately. Two things still need **one online session** to populate, exactly
like the web app:

- **Import your KML lines** (or use the built-ins), and
- **Download imagery** (and elevation, which rides along) for the areas you patrol —
  Map key → Along pipelines → Download.

After that, put the iPad in Airplane Mode and confirm the map, your lines, and elevation
all work with no signal. Because it's a real app, this downloaded data is durable — it
won't be evicted the way a Safari tab's data can be.

---

## Distributing to the fleet

- **A few iPads you have on hand:** connect each and Run from Xcode (paid account =
  permanent; free account = reinstall weekly).
- **The whole fleet, over the air:** with a paid Developer account, use **TestFlight**
  (Xcode → Product → Archive → Distribute App → App Store Connect → TestFlight). Crews
  install the TestFlight app and get your builds without a cable. This is the recommended
  route for a fleet.

---

## Updating the app later

When the web app changes (e.g. a new `index.html` from the repo):

```bash
npm run copy:web
npx cap sync ios
npx cap open ios
```

Then Run/Archive again. Downloaded imagery, lines, and pins on each device are kept across
app updates (they live in the app's own storage, not in the app bundle).

---

## Notes / troubleshooting

- **Imagery download in the app** uses the same image servers as the web app and relies on
  them sending CORS headers (they do). If a future imagery source ever refuses CORS in the
  native WebView, the fix is to route that one download through Capacitor's HTTP plugin —
  ask and it can be added; nothing else would change.
- **Storage:** the app requests persistent storage automatically. A native app's quota is
  far larger than a Safari tab's, so multi-GB imagery downloads are fine given the iPad has
  the free space.
- **`dem.bin` is optional.** Without it, elevation still works — it's downloaded along the
  imagery corridor and stored on the device. `dem.bin` is only a bundled base layer of
  terrain if you choose to build one (see the main README).
- **App icon / name:** set in Xcode (App target → General, and the `Assets.xcassets`
  AppIcon). The bundled `icon-512.png` can be used as the source image.
