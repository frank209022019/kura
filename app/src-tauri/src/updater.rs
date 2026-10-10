//! Updates from Kura's private GitHub releases.
//!
//! The repo is private, so this PC's GitHub CLI login opens the door: `gh` finds
//! the update manifest (latest.json) of the newest release, and the updater
//! downloads the installer with the same login. Before anything runs, the
//! installer's signature is checked against the public key in tauri.conf.json.
//! See docs/releasing.md.

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, State, Url};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::engine::{self, Engine};
use crate::process;

const REPO: &str = "frankgrobbelaar/kura";

/// Mirrors `ReadyUpdate` in app/src/lib/updates.ts.
#[derive(Serialize)]
pub struct ReadyUpdate {
    version: String,
}

/// An update that has been downloaded and is waiting for "Restart and update".
#[derive(Default)]
pub struct PendingUpdate(Mutex<Option<(Update, Vec<u8>)>>);

/// Checks for a newer Kura and downloads it. Returns `None` when Kura is up to date.
#[tauri::command]
pub async fn prepare_update(
    app: AppHandle,
    pending: State<'_, PendingUpdate>,
) -> Result<Option<ReadyUpdate>, String> {
    let token = gh(&["auth", "token"])?;
    let Some(manifest) = latest_manifest()? else {
        return Ok(None);
    };

    let update = app
        .updater_builder()
        .endpoints(vec![manifest])
        .map_err(text)?
        .header("Authorization", format!("Bearer {token}"))
        .map_err(text)?
        .header("Accept", "application/octet-stream")
        .map_err(text)?
        .build()
        .map_err(text)?
        .check()
        .await
        .map_err(text)?;
    let Some(update) = update else {
        return Ok(None);
    };

    let bytes = update.download(|_, _| {}, || {}).await.map_err(text)?;
    let ready = ReadyUpdate {
        version: update.version.clone(),
    };
    *pending.0.lock().unwrap() = Some((update, bytes));
    Ok(Some(ready))
}

/// Stops the engine and runs the installer. Kura closes, and the installer opens it again.
/// If the installer can't start, the engine is started again so Kura keeps working.
#[tauri::command]
pub fn install_update(
    app: AppHandle,
    pending: State<'_, PendingUpdate>,
    engine: State<'_, Engine>,
) -> Result<(), String> {
    let (update, bytes) = pending
        .0
        .lock()
        .unwrap()
        .take()
        .ok_or("No update is ready to install.")?;
    engine.stop(); // the installer replaces the engine's files
    update.install(bytes).map_err(|error| {
        engine::start(app);
        text(error)
    })
}

/// The API address of the newest release's latest.json, or `None` if there is no release yet.
fn latest_manifest() -> Result<Option<Url>, String> {
    let release = format!("repos/{REPO}/releases/latest");
    let query = r#".assets[] | select(.name == "latest.json") | .url"#;
    match gh(&["api", &release, "--jq", query]) {
        Ok(url) if url.is_empty() => Ok(None),
        Ok(url) => Url::parse(&url).map(Some).map_err(text),
        Err(message) if message.contains("HTTP 404") => Ok(None),
        Err(message) => Err(message),
    }
}

/// Runs the GitHub CLI and returns what it printed.
fn gh(args: &[&str]) -> Result<String, String> {
    let output = process::hidden("gh").args(args).output().map_err(|_| {
        "Updates use the GitHub CLI. Install it and sign in with `gh auth login`.".to_string()
    })?;
    if !output.status.success() {
        let said = String::from_utf8_lossy(&output.stderr);
        return Err(format!("The GitHub CLI said: {}", said.trim()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn text(error: impl std::fmt::Display) -> String {
    error.to_string()
}
