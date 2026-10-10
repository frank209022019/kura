//! Starts Kura's engine (the Python program beside the window) and tells the UI
//! where to reach it.
//!
//! The handshake, also tested from the engine's side in engine/tests/test_cli.py:
//! - the shell starts `kura serve --watch-stdin` with a fresh token in KURA_TOKEN;
//! - the engine prints one JSON line once it listens: {"event":"ready","port":N};
//! - the engine stops by itself when its stdin closes, so it never outlives the app.
//!
//! If the engine stops on its own, before or after it was ready, the status becomes
//! `failed` with its last error lines, and the UI offers to try again.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Read};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex, mpsc};
use std::thread;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::process;

/// How long the engine may take to start. The first launch after an install is the slowest.
const START_TIMEOUT: Duration = Duration::from_secs(60);
/// How many of the engine's last error lines to keep for "Copy details".
const ERROR_LINES: usize = 40;

/// What the UI sees. Mirrors `EngineStatus` in app/src/lib/engine.tsx.
#[derive(Clone, Default, Serialize)]
#[serde(tag = "state", rename_all = "camelCase")]
pub enum EngineStatus {
    #[default]
    Starting,
    Ready {
        url: String,
        token: String,
    },
    Failed {
        message: String,
        details: String,
    },
}

#[derive(Default)]
pub struct Engine {
    status: Mutex<EngineStatus>,
    running: Mutex<Option<Running>>,
}

struct Running {
    child: Child,
    /// Dropping this closes the pipe, which tells the engine to stop.
    stdin: ChildStdin,
}

impl Engine {
    /// Asks the engine to stop by closing its stdin, and ends it if it is still running after 3 seconds.
    pub fn stop(&self) {
        let Some(Running { mut child, stdin }) = self.running.lock().unwrap().take() else {
            return;
        };
        drop(stdin);
        for _ in 0..30 {
            if matches!(child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let _ = child.kill();
        let _ = child.wait();
    }

    /// Called once an engine has exited. If it was still the current engine, nobody stopped
    /// it on purpose: it crashed. Either way, it is forgotten.
    fn ended_unexpectedly(&self, pid: u32) -> bool {
        let mut running = self.running.lock().unwrap();
        match running.take_if(|engine| engine.child.id() == pid) {
            Some(mut engine) => {
                let _ = engine.child.wait();
                true
            }
            None => false,
        }
    }
}

/// Starts the engine in the background. The UI follows along through `engine-status` events.
pub fn start(app: AppHandle) {
    set_status(&app, EngineStatus::Starting);
    thread::spawn(move || {
        let started = match launch(&app) {
            Ok(started) => started,
            Err(failure) => return set_status(&app, failure),
        };
        set_status(
            &app,
            EngineStatus::Ready {
                url: started.url,
                token: started.token,
            },
        );

        let _ = started.exited.recv(); // returns once the engine has exited
        if app.state::<Engine>().ended_unexpectedly(started.pid) {
            set_status(
                &app,
                failed("It stopped unexpectedly.", started.errors.text()),
            );
        }
    });
}

#[tauri::command]
pub fn engine_status(engine: State<'_, Engine>) -> EngineStatus {
    engine.status.lock().unwrap().clone()
}

/// Tries again after a failure. Does nothing while the engine is already starting.
#[tauri::command]
pub fn restart_engine(app: AppHandle, engine: State<'_, Engine>) {
    {
        let mut status = engine.status.lock().unwrap();
        if matches!(*status, EngineStatus::Starting) {
            return;
        }
        *status = EngineStatus::Starting;
    }
    engine.stop();
    start(app);
}

/// A started engine, and what it takes to notice if it stops on its own.
struct Started {
    url: String,
    token: String,
    pid: u32,
    /// `recv()` on this returns once the engine's output closes, which is when it exits.
    exited: mpsc::Receiver<u16>,
    errors: ErrorLog,
}

fn launch(app: &AppHandle) -> Result<Started, EngineStatus> {
    let mut command = engine_command(app).map_err(|message| failed(message, String::new()))?;
    let token = new_token();
    command
        .args(["serve", "--watch-stdin"])
        .env("KURA_TOKEN", &token)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command.spawn().map_err(|error| {
        // Name the program, but not the environment: it holds the token.
        let program = command.get_program().to_string_lossy().into_owned();
        failed(format!("Windows couldn't run it ({error})."), program)
    })?;
    let pid = child.id();
    let stdin = child.stdin.take().expect("stdin is piped");
    let errors = ErrorLog::follow(child.stderr.take().expect("stderr is piped"));

    match wait_for_port(child.stdout.take().expect("stdout is piped")) {
        Ok((port, exited)) => {
            *app.state::<Engine>().running.lock().unwrap() = Some(Running { child, stdin });
            Ok(Started {
                url: format!("http://127.0.0.1:{port}"),
                token,
                pid,
                exited,
                errors,
            })
        }
        Err(problem) => {
            let _ = child.kill();
            let _ = child.wait();
            let message = match problem {
                NotReady::TimedOut => "It didn't answer within a minute.",
                NotReady::Exited => "It stopped before it was ready.",
            };
            Err(failed(message, errors.text()))
        }
    }
}

/// In development the engine runs from source with uv, keeping its data in
/// engine/.dev-data so development never touches the real data in %LOCALAPPDATA%\Kura.
/// Installed, it is the bundled kura-engine.exe.
fn engine_command(app: &AppHandle) -> Result<Command, String> {
    if cfg!(debug_assertions) {
        let source = concat!(env!("CARGO_MANIFEST_DIR"), "/../../engine");
        let mut command = process::hidden("uv");
        command.args(["run", "--project", source, "kura"]);
        if std::env::var_os("KURA_DATA_DIR").is_none() {
            command.env("KURA_DATA_DIR", format!("{source}/.dev-data"));
        }
        Ok(command)
    } else {
        let resources = app
            .path()
            .resource_dir()
            .map_err(|error| format!("Kura couldn't find its own files ({error})."))?;
        Ok(process::hidden(
            resources.join("engine").join("kura-engine.exe"),
        ))
    }
}

/// A fresh secret for every launch, so only this window can talk to this engine.
fn new_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("Windows always provides random bytes");
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[derive(Debug)]
enum NotReady {
    TimedOut,
    Exited,
}

#[derive(Deserialize)]
struct Announcement {
    event: String,
    port: u16,
}

/// Reads the engine's stdout until it announces its port. Reading carries on, throwing the
/// rest away so the engine never stalls on a full pipe, until the engine exits and its
/// output closes; that is when `recv()` on the returned receiver comes back.
fn wait_for_port(
    stdout: impl Read + Send + 'static,
) -> Result<(u16, mpsc::Receiver<u16>), NotReady> {
    let (announce, announced) = mpsc::channel();
    thread::spawn(move || {
        let mut lines = BufReader::new(stdout).lines().map_while(Result::ok);
        for line in lines.by_ref() {
            if let Ok(Announcement { event, port }) = serde_json::from_str(&line)
                && event == "ready"
            {
                let _ = announce.send(port);
                break;
            }
        }
        lines.for_each(drop);
    });
    match announced.recv_timeout(START_TIMEOUT) {
        Ok(port) => Ok((port, announced)),
        Err(mpsc::RecvTimeoutError::Timeout) => Err(NotReady::TimedOut),
        Err(mpsc::RecvTimeoutError::Disconnected) => Err(NotReady::Exited),
    }
}

/// The engine's last few stderr lines, for the failure report.
struct ErrorLog {
    lines: Arc<Mutex<VecDeque<String>>>,
    finished: mpsc::Receiver<()>,
}

impl ErrorLog {
    fn follow(stderr: impl Read + Send + 'static) -> Self {
        let lines = Arc::new(Mutex::new(VecDeque::with_capacity(ERROR_LINES)));
        let (done, finished) = mpsc::channel();
        let kept = Arc::clone(&lines);
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                let mut kept = kept.lock().unwrap();
                if kept.len() == ERROR_LINES {
                    kept.pop_front();
                }
                kept.push_back(line);
            }
            let _ = done.send(());
        });
        Self { lines, finished }
    }

    /// Everything kept so far, after giving the engine a moment to finish writing.
    fn text(&self) -> String {
        let _ = self.finished.recv_timeout(Duration::from_secs(1));
        let lines = self.lines.lock().unwrap();
        lines.iter().cloned().collect::<Vec<_>>().join("\n")
    }
}

fn set_status(app: &AppHandle, status: EngineStatus) {
    *app.state::<Engine>().status.lock().unwrap() = status.clone();
    let _ = app.emit("engine-status", status);
}

fn failed(message: impl Into<String>, details: String) -> EngineStatus {
    EngineStatus::Failed {
        message: message.into(),
        details,
    }
}

#[cfg(test)]
mod tests {
    use std::io::Cursor;

    use super::*;

    const READY: &str = "{\"event\":\"ready\",\"port\":51234}\n";

    #[test]
    fn finds_the_port_in_the_ready_line() {
        let stdout = Cursor::new(format!("starting\n{READY}"));
        assert!(matches!(wait_for_port(stdout), Ok((51234, _))));
    }

    #[test]
    fn notices_when_the_engine_exits_without_announcing_a_port() {
        let stdout = Cursor::new("Traceback (most recent call last):\n");
        assert!(matches!(wait_for_port(stdout), Err(NotReady::Exited)));
    }

    #[test]
    fn notices_when_the_engine_exits_after_starting() {
        let stdout = Cursor::new(format!("{READY}{READY}later output\n"));
        let (_, exited) = wait_for_port(stdout).expect("a port");
        assert!(
            exited.recv().is_err(),
            "only one announcement, then the end"
        );
    }

    #[test]
    fn keeps_only_the_last_error_lines() {
        let stderr: String = (1..=50).map(|n| format!("line {n}\n")).collect();
        let kept = ErrorLog::follow(Cursor::new(stderr)).text();
        assert!(kept.starts_with("line 11\n"));
        assert!(kept.ends_with("line 50"));
    }

    #[test]
    fn every_launch_gets_a_new_long_token() {
        let (first, second) = (new_token(), new_token());
        assert_eq!(first.len(), 64);
        assert_ne!(first, second);
    }
}
