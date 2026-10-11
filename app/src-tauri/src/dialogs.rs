//! Windows' own dialogs. The shell opens them, so the window needs no dialog permission.

use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

/// Asks for a folder with Windows' folder picker. `None` when it's cancelled.
#[tauri::command]
pub async fn pick_folder(app: AppHandle, title: String) -> Result<Option<String>, String> {
    let picked = tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().set_title(title).blocking_pick_folder()
    })
    .await
    .map_err(|error| error.to_string())?;
    Ok(picked
        .and_then(|folder| folder.into_path().ok())
        .map(|folder| folder.display().to_string()))
}
