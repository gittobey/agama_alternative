<!-- Install the service (requires admin) -->
AgentService.exe install

<!--  Start the service -->
AgentService.exe start

<!-- Ensure proper service registration:
powershell -->
sc create AgentMonitor binPath= "C:\path\to\AgentService.exe" start= auto
sc start AgentMonitor