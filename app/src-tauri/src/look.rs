//! Light or dark: as Windows is (the default), or always one, as the owner chose in Settings >
//! General. The window's theme carries it to the page, whose colours follow it
//! (app/src/styles/tokens.css), and the window's own colour under the page follows too.

use serde::{Deserialize, Serialize};
use tauri::window::Color;
use tauri::{AppHandle, Manager, Theme, WebviewWindow, WebviewWindowBuilder, Window};

use crate::choices;

/// The owner's choice. Mirrors `Look` in app/src/lib/look.ts.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Look {
    /// Light or dark as Windows is, changing when it does.
    #[default]
    Windows,
    Light,
    Dark,
}

impl Look {
    /// The window's own theme: none follows Windows.
    fn theme(self) -> Option<Theme> {
        match self {
            Look::Windows => None,
            Look::Light => Some(Theme::Light),
            Look::Dark => Some(Theme::Dark),
        }
    }
}

const CHOICE: &str = "look";

/// The look chosen; as Windows is when none was.
fn saved(app: &AppHandle) -> Look {
    choices::read(app, CHOICE)
        .and_then(|value| serde_json::from_value(value).ok())
        .unwrap_or_default()
}

/// The window's own colour, under the page: the page's window colour (--color-window) in each.
fn window_colour(theme: Theme) -> Color {
    match theme {
        Theme::Light => Color(0xf3, 0xef, 0xe6, 0xff),
        _ => Color(0x0b, 0x0c, 0x0f, 0xff),
    }
}

/// Makes Kura's window, hidden, in the look chosen, so the page is light or dark from its first
/// frame. Everything else about the window is in tauri.conf.json.
pub fn make_window(app: &AppHandle) -> tauri::Result<WebviewWindow> {
    let config = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .ok_or(tauri::Error::WindowNotFound)?;
    let window = WebviewWindowBuilder::from_config(app, config)?
        .theme(saved(app).theme())
        .build()?;
    window.set_background_color(Some(window_colour(window.theme()?)))?;
    Ok(window)
}

/// The window's colour follows its theme when that changes: Windows' own, or the owner's choice.
pub fn follow(window: &Window, theme: Theme) {
    if let Some(window) = window.app_handle().get_webview_window(window.label()) {
        let _ = window.set_background_color(Some(window_colour(theme)));
    }
}

/// The look chosen.
#[tauri::command]
pub fn look(app: AppHandle) -> Result<Look, String> {
    Ok(saved(&app))
}

/// Chooses the look: from now, and at every start.
#[tauri::command]
pub fn set_look(app: AppHandle, look: Look) -> Result<Look, String> {
    let value = serde_json::to_value(look).map_err(|error| error.to_string())?;
    choices::save(&app, CHOICE, value)?;
    if let Some(window) = app.get_webview_window("main") {
        window
            .set_theme(look.theme())
            .map_err(|error| format!("Windows didn't take that ({error})."))?;
    }
    Ok(look)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_look_reads_as_the_page_writes_it() {
        for (look, word) in [
            (Look::Windows, "windows"),
            (Look::Light, "light"),
            (Look::Dark, "dark"),
        ] {
            assert_eq!(serde_json::to_value(look).unwrap(), json!(word));
            assert_eq!(serde_json::from_value::<Look>(json!(word)).unwrap(), look);
        }
    }

    #[test]
    fn same_as_windows_gives_the_window_no_theme_of_its_own() {
        assert_eq!(Look::Windows.theme(), None);
        assert_eq!(Look::Light.theme(), Some(Theme::Light));
        assert_eq!(Look::Dark.theme(), Some(Theme::Dark));
        assert_eq!(Look::default(), Look::Windows);
    }

    #[test]
    fn the_window_is_the_colour_of_the_page() {
        assert_eq!(window_colour(Theme::Light), Color(0xf3, 0xef, 0xe6, 0xff));
        assert_eq!(window_colour(Theme::Dark), Color(0x0b, 0x0c, 0x0f, 0xff));
    }
}
