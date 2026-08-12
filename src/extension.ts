import * as cp from 'node:child_process';
import * as net from 'node:net';
import * as path from 'node:path';
import * as readline from 'node:readline';
import * as vscode from 'vscode';

const DEFAULT_HOST = 'localhost';
const DEFAULT_PORTS = [80, 8000, 8080];

let serverProcess: cp.ChildProcessWithoutNullStreams | undefined;
let serverUrl: string | undefined;
let statusBarItem: vscode.StatusBarItem;
let stopStatusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;

type PythonEnvironmentPath = {
  path?: string;
};

type PythonEnvironment = {
  executable?: {
    uri?: vscode.Uri;
    filename?: string;
    sysPrefix?: string;
  };
};

type PythonExtensionApi = {
  environments?: {
    getActiveEnvironmentPath?: (resource?: vscode.Uri) => PythonEnvironmentPath;
    resolveEnvironment?: (environmentPath: PythonEnvironmentPath) => Promise<PythonEnvironment | undefined>;
  };
};

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel('TIP Server');
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.name = 'TIP Server';
  stopStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  stopStatusBarItem.name = 'Stop TIP Server';
  stopStatusBarItem.text = '$(debug-stop)';
  stopStatusBarItem.tooltip = 'Stop TIP Server';
  stopStatusBarItem.command = 'tipServer.stop';

  context.subscriptions.push(
    outputChannel,
    statusBarItem,
    stopStatusBarItem,
    vscode.commands.registerCommand('tipServer.start', () => startServer(context)),
    vscode.commands.registerCommand('tipServer.stop', stopServer),
    vscode.commands.registerCommand('tipServer.toggle', () => toggleServer(context)),
    vscode.commands.registerCommand('tipServer.open', openServerUrl),
    vscode.workspace.onDidChangeWorkspaceFolders(() => configurePylanceTipPath(context))
  );

  updateStatusBar();
  statusBarItem.show();

  void configurePylanceTipPath(context);
}

export async function deactivate(): Promise<void> {
  await stopServer();
}

async function toggleServer(context: vscode.ExtensionContext): Promise<void> {
  if (serverProcess) {
    await stopServer();
    return;
  }

  await startServer(context);
}

async function startServer(context: vscode.ExtensionContext): Promise<void> {
  if (serverProcess) {
    await openServerUrl();
    return;
  }

  const workspaceFolder = getSingleWorkspaceFolder();
  if (!workspaceFolder) {
    return;
  }

  const serverScript = vscode.Uri.joinPath(context.extensionUri, 'resources', 'tip_server.py').fsPath;
  const pythonExecutable = await resolvePythonExecutable(workspaceFolder.uri);
  const ports = await getAvailablePorts(DEFAULT_PORTS);

  if (ports.length === 0) {
    void vscode.window.showErrorMessage(`TIP Server could not find a free port among ${DEFAULT_PORTS.join(', ')}.`);
    return;
  }

  outputChannel.clear();
  outputChannel.appendLine(`Starting TIP Server for ${workspaceFolder.uri.fsPath}`);
  outputChannel.appendLine(`Python: ${pythonExecutable}`);
  outputChannel.appendLine(`Script: ${serverScript}`);

  serverProcess = cp.spawn(
    pythonExecutable,
    ['-u', serverScript, workspaceFolder.uri.fsPath, '--ports', ports.join(',')],
    {
      cwd: workspaceFolder.uri.fsPath,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      windowsHide: true
    }
  );

  serverProcess.once('exit', (code, signal) => {
    outputChannel.appendLine(`TIP Server stopped. Exit code: ${code ?? 'none'}, signal: ${signal ?? 'none'}`);
    serverProcess = undefined;
    serverUrl = undefined;
    updateStatusBar();
  });

  serverProcess.once('error', error => {
    outputChannel.appendLine(`Could not start TIP Server: ${error.message}`);
    void vscode.window.showErrorMessage(`Could not start TIP Server: ${error.message}`);
    serverProcess = undefined;
    serverUrl = undefined;
    updateStatusBar();
  });

  attachServerOutput(serverProcess);
  serverUrl = await waitForServerUrl(serverProcess);
  updateStatusBar();

  if (serverUrl) {
    void vscode.window.showInformationMessage(`TIP Server started at ${serverUrl}`);
  }
}

async function configurePylanceTipPath(context: vscode.ExtensionContext): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) {
    return;
  }

  if (folders.length !== 1) {
    return;
  }

  const stubRoot = vscode.Uri.joinPath(context.extensionUri, 'resources', 'pylance').fsPath;

  for (const folder of folders) {
    const analysisConfig = vscode.workspace.getConfiguration('python.analysis', folder.uri);
    const existingExtraPaths = analysisConfig.get<string[]>('extraPaths') ?? [];

    if (existingExtraPaths.includes(stubRoot)) {
      continue;
    }

    await analysisConfig.update(
      'extraPaths',
      [...existingExtraPaths, stubRoot],
      vscode.ConfigurationTarget.WorkspaceFolder
    );
  }
}

async function stopServer(): Promise<void> {
  if (!serverProcess) {
    updateStatusBar();
    return;
  }

  const processToStop = serverProcess;
  serverProcess = undefined;
  serverUrl = undefined;
  updateStatusBar();

  await new Promise<void>(resolve => {
    const timeout = setTimeout(() => {
      if (!processToStop.killed) {
        processToStop.kill('SIGKILL');
      }
      resolve();
    }, 1500);

    processToStop.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });

    processToStop.kill();
  });
}

async function openServerUrl(): Promise<void> {
  if (!serverUrl) {
    void vscode.window.showInformationMessage('TIP Server is not running.');
    return;
  }

  await vscode.env.openExternal(vscode.Uri.parse(serverUrl));
}

function getSingleWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders;

  if (!folders || folders.length === 0) {
    void vscode.window.showErrorMessage('Open a folder before starting TIP Server.');
    return undefined;
  }

  if (folders.length === 1) {
    return folders[0];
  }

  void vscode.window.showErrorMessage('TIP Server works with one opened folder at a time. Please open the project folder directly.');
  return undefined;
}

async function resolvePythonExecutable(resource: vscode.Uri): Promise<string> {
  const pythonExtension = vscode.extensions.getExtension<PythonExtensionApi>('ms-python.python');

  if (pythonExtension) {
    const api = pythonExtension.isActive ? pythonExtension.exports : await pythonExtension.activate();
    const environmentPath = api.environments?.getActiveEnvironmentPath?.(resource);

    if (environmentPath) {
      const environment = await api.environments?.resolveEnvironment?.(environmentPath);
      const executable = environment?.executable?.uri?.fsPath ?? environment?.executable?.filename;

      if (executable) {
        return executable;
      }

      if (environmentPath.path && path.basename(environmentPath.path).toLowerCase().startsWith('python')) {
        return environmentPath.path;
      }
    }
  }

  const configuredPath = vscode.workspace.getConfiguration('python', resource).get<string>('defaultInterpreterPath');
  if (configuredPath) {
    return configuredPath;
  }

  return process.platform === 'win32' ? 'python' : 'python3';
}

async function getAvailablePorts(ports: number[]): Promise<number[]> {
  const checks = await Promise.all(ports.map(async port => ({ port, available: await isPortAvailable(port) })));
  return checks.filter(check => check.available).map(check => check.port);
}

function isPortAvailable(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const server = net.createServer();

    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, DEFAULT_HOST);
  });
}

function attachServerOutput(processToRead: cp.ChildProcessWithoutNullStreams): void {
  processToRead.stdout.on('data', chunk => outputChannel.append(chunk.toString()));
  processToRead.stderr.on('data', chunk => outputChannel.append(chunk.toString()));
}

function waitForServerUrl(processToRead: cp.ChildProcessWithoutNullStreams): Promise<string | undefined> {
  return new Promise(resolve => {
    const timeout = setTimeout(() => resolve(undefined), 5000);
    const lines = readline.createInterface({ input: processToRead.stdout });

    lines.on('line', line => {
      const match = line.match(/Serving .+ at (http:\/\/[^\s]+)/);
      if (!match) {
        return;
      }

      clearTimeout(timeout);
      lines.close();
      resolve(match[1]);
    });

    processToRead.once('exit', () => {
      clearTimeout(timeout);
      lines.close();
      resolve(undefined);
    });
  });
}

function updateStatusBar(): void {
  if (!statusBarItem) {
    return;
  }

  if (serverProcess && serverUrl) {
    statusBarItem.text = `$(globe) TIP ${serverUrl}`;
    statusBarItem.tooltip = 'Open TIP Server in browser';
    statusBarItem.command = 'tipServer.open';
    stopStatusBarItem.show();
    return;
  }

  if (serverProcess) {
    statusBarItem.text = '$(sync~spin) TIP Starting';
    statusBarItem.tooltip = 'TIP Server is starting';
    statusBarItem.command = undefined;
    stopStatusBarItem.show();
    return;
  }

  statusBarItem.text = '$(play) TIP Server';
  statusBarItem.tooltip = 'Start TIP Server for the current folder';
  statusBarItem.command = 'tipServer.start';
  stopStatusBarItem.hide();
}
