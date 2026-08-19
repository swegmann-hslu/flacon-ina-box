import * as cp from 'node:child_process';
import * as net from 'node:net';
import * as path from 'node:path';
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
  outputChannel = vscode.window.createOutputChannel('Flacon');
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.name = 'Flacon';
  stopStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  stopStatusBarItem.name = 'Stop Flacon';
  stopStatusBarItem.text = '$(debug-stop)';
  stopStatusBarItem.tooltip = 'Stop Flacon';
  stopStatusBarItem.command = 'flacon.stop';

  context.subscriptions.push(
    outputChannel,
    statusBarItem,
    stopStatusBarItem,
    vscode.commands.registerCommand('flacon.start', () => startServer(context)),
    vscode.commands.registerCommand('flacon.stop', stopServer),
    vscode.commands.registerCommand('flacon.toggle', () => toggleServer(context)),
    vscode.commands.registerCommand('flacon.open', openServerUrl),
    vscode.commands.registerCommand('flacon.fixPylancePath', () => configurePylancePath(context))
  );

  updateStatusBar();
  statusBarItem.show();
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

  const serverScript = vscode.Uri.joinPath(context.extensionUri, 'resources', 'flacon_server.py').fsPath;
  const pythonExecutable = await resolvePythonExecutable(workspaceFolder.uri);
  const ports = await getAvailablePorts(DEFAULT_PORTS);

  if (ports.length === 0) {
    void vscode.window.showErrorMessage(`Flacon could not find a free port among ${DEFAULT_PORTS.join(', ')}.`);
    return;
  }

  outputChannel.clear();
  outputChannel.show(true);
  outputChannel.appendLine(`Starting Flacon for ${workspaceFolder.uri.fsPath}`);
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
    outputChannel.appendLine(`Flacon stopped. Exit code: ${code ?? 'none'}, signal: ${signal ?? 'none'}`);
    serverProcess = undefined;
    serverUrl = undefined;
    updateStatusBar();
  });

  serverProcess.once('error', error => {
    outputChannel.appendLine(`Could not start Flacon: ${error.message}`);
    void vscode.window.showErrorMessage(`Could not start Flacon: ${error.message}`);
    serverProcess = undefined;
    serverUrl = undefined;
    updateStatusBar();
  });

  serverUrl = await attachServerOutput(serverProcess);
  updateStatusBar();

  if (serverUrl) {
    void vscode.window.showInformationMessage(`Flacon started at ${serverUrl}`);
  }
}

async function configurePylancePath(context: vscode.ExtensionContext): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) {
    void vscode.window.showErrorMessage('Open a folder before configuring Pylance for Flacon.');
    return;
  }

  if (folders.length !== 1) {
    void vscode.window.showErrorMessage('Flacon works with one opened folder at a time. Please open the project folder directly.');
    return;
  }

  const stubRoot = vscode.Uri.joinPath(context.extensionUri, 'resources', 'pylance').fsPath;

  for (const folder of folders) {
    const analysisConfig = vscode.workspace.getConfiguration('python.analysis', folder.uri);
    const existingExtraPaths = analysisConfig.get<string[]>('extraPaths') ?? [];

    if (existingExtraPaths.includes(stubRoot)) {
      void vscode.window.showInformationMessage('Pylance is already configured for Flacon in this workspace.');
      continue;
    }

    await analysisConfig.update(
      'extraPaths',
      [...existingExtraPaths, stubRoot],
      vscode.ConfigurationTarget.WorkspaceFolder
    );

    void vscode.window.showInformationMessage('Configured Pylance for Flacon in this workspace.');
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
    void vscode.window.showInformationMessage('Flacon is not running.');
    return;
  }

  await vscode.env.openExternal(vscode.Uri.parse(serverUrl));
}

function getSingleWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders;

  if (!folders || folders.length === 0) {
    void vscode.window.showErrorMessage('Open a folder before starting Flacon.');
    return undefined;
  }

  if (folders.length === 1) {
    return folders[0];
  }

  void vscode.window.showErrorMessage('Flacon works with one opened folder at a time. Please open the project folder directly.');
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

function attachServerOutput(processToRead: cp.ChildProcessWithoutNullStreams): Promise<string | undefined> {
  return new Promise(resolve => {
    let resolved = false;
    let stdoutBuffer = '';
    const timeout = setTimeout(() => resolveServerUrl(undefined), 5000);

    function resolveServerUrl(url: string | undefined): void {
      if (resolved) {
        return;
      }

      resolved = true;
      clearTimeout(timeout);
      resolve(url);
    }

    processToRead.stdout.on('data', chunk => {
      const text = chunk.toString();
      outputChannel.append(text);

      stdoutBuffer += text;
      const match = stdoutBuffer.match(/Serving .+ at (http:\/\/[^\s]+)/);
      if (!match) {
        return;
      }

      resolveServerUrl(match[1]);
    });

    processToRead.stderr.on('data', chunk => outputChannel.append(chunk.toString()));

    processToRead.once('exit', () => resolveServerUrl(undefined));
  });
}

function updateStatusBar(): void {
  if (!statusBarItem) {
    return;
  }

  if (serverProcess && serverUrl) {
    statusBarItem.text = `$(globe) Flacon ${serverUrl}`;
    statusBarItem.tooltip = 'Open Flacon in browser';
    statusBarItem.command = 'flacon.open';
    stopStatusBarItem.show();
    return;
  }

  if (serverProcess) {
    statusBarItem.text = '$(sync~spin) Flacon Starting';
    statusBarItem.tooltip = 'Flacon is starting';
    statusBarItem.command = undefined;
    stopStatusBarItem.show();
    return;
  }

  statusBarItem.text = '$(play) Flacon';
  statusBarItem.tooltip = 'Start Flacon for the current folder';
  statusBarItem.command = 'flacon.start';
  stopStatusBarItem.hide();
}
