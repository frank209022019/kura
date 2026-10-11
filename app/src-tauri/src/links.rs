//! Pages Kura opens in the browser. The window can't open addresses itself: it asks for one of
//! these by name, so it can never be steered anywhere else.

use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

/// Every released version, newest first, with what changed and its installer.
/// Built by scripts/downloads-page.mjs; see docs/releasing.md.
pub const DOWNLOADS_PAGE: &str = "https://frankgrobbelaar.github.io/kura/";

/// Opens the downloads page in the default browser.
#[tauri::command]
pub fn open_downloads_page(app: AppHandle) -> Result<(), String> {
    app.opener()
        .open_url(DOWNLOADS_PAGE, None::<&str>)
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::DOWNLOADS_PAGE;

    #[test]
    fn the_downloads_page_is_kuras_own_secure_site() {
        assert!(DOWNLOADS_PAGE.starts_with("https://frankgrobbelaar.github.io/kura"));
    }
}
