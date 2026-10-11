//! Pages Kura opens in the browser. The window can't open addresses itself: it asks for one of
//! these by name, so it can never be steered anywhere else.

use tauri::AppHandle;
use tauri_plugin_opener::OpenerExt;

/// Every released version, newest first, with what changed and its installer.
/// Built by scripts/downloads-page.mjs; see docs/releasing.md.
pub const DOWNLOADS_PAGE: &str = "https://frankgrobbelaar.github.io/kura/";

/// Where a TMDB account's keys are, for the TMDB key in Setup.
pub const TMDB_API_PAGE: &str = "https://www.themoviedb.org/settings/api";

/// Opens the downloads page in the default browser.
#[tauri::command]
pub fn open_downloads_page(app: AppHandle) -> Result<(), String> {
    open(&app, DOWNLOADS_PAGE)
}

/// Opens TMDB's page with the account's API keys in the default browser.
#[tauri::command]
pub fn open_tmdb_api_page(app: AppHandle) -> Result<(), String> {
    open(&app, TMDB_API_PAGE)
}

fn open(app: &AppHandle, address: &str) -> Result<(), String> {
    app.opener()
        .open_url(address, None::<&str>)
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::{DOWNLOADS_PAGE, TMDB_API_PAGE};

    #[test]
    fn the_downloads_page_is_kuras_own_secure_site() {
        assert!(DOWNLOADS_PAGE.starts_with("https://frankgrobbelaar.github.io/kura"));
    }

    #[test]
    fn the_tmdb_page_is_tmdbs_own_secure_site() {
        assert!(TMDB_API_PAGE.starts_with("https://www.themoviedb.org/"));
    }
}
