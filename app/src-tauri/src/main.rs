// Kura's desktop shell: one window for the UI, with the engine running beside it.
// See docs/stack/tauri.md.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod dialogs;
mod engine;
mod explorer;
mod links;
mod process;
mod updater;

use tauri::{Manager, RunEvent};

fn main() {
    let app = tauri::Builder::default()
        // Opening Kura again focuses the window that's already open:
        // two copies would share one database.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(engine::Engine::default())
        .manage(updater::PendingUpdate::default())
        .invoke_handler(tauri::generate_handler![
            engine::engine_status,
            engine::restart_engine,
            updater::prepare_update,
            updater::install_update,
            links::open_downloads_page,
            links::open_tmdb_api_page,
            dialogs::pick_folder,
            explorer::open_folder,
            explorer::show_in_folder,
        ])
        .setup(|app| {
            engine::start(app.handle().clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Kura's window couldn't be created");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            app.state::<engine::Engine>().stop();
        }
    });
}
