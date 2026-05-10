import SwiftUI

struct ContentView: View {
    @State private var backendMode: BackendMode = .render
    @State private var locationText = "New York, NY"
    @State private var scenario: Scenario = .flood

    @State private var selectedLocation: GeocodeResult?
    @State private var weather: WeatherResponse?
    @State private var alerts: AlertsResponse?
    @State private var resources: ResourcesResponse?
    @State private var risk: RiskResponse?
    @State private var plan: PlanResponse?

    @State private var isFindingLocation = false
    @State private var isFetchingData = false
    @State private var isGeneratingPlan = false
    @State private var errorMessage: String?

    private var baseURL: String {
        backendMode.baseURL
    }

    private var inferredScenario: Scenario {
        scenarioFromAlerts()
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    headerCard
                    backendCard
                    locationCard

                    if let selectedLocation {
                        selectedLocationCard(selectedLocation)
                        scenarioCard
                        situationButtonCard
                    }

                    if weather != nil || alerts != nil || resources != nil || risk != nil {
                        situationCards
                    }

                    if selectedLocation != nil {
                        planButtonCard
                    }

                    if let plan {
                        planCard(plan)
                    }

                    if let errorMessage {
                        errorCard(errorMessage)
                    }
                }
                .padding()
            }
            .navigationTitle("Evac-AI")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    // MARK: - Header

    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Evac-AI")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("AI-powered emergency preparedness with live alerts, weather, nearby help, ML risk prediction, and IBM watsonx action plans.")
                .font(.body)
                .foregroundStyle(.secondary)

            HStack {
                Label("Live APIs", systemImage: "antenna.radiowaves.left.and.right")
                Spacer()
                Label("IBM watsonx", systemImage: "sparkles")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .card()
    }

    private var backendCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Backend")
                .font(.headline)

            Picker("Backend", selection: $backendMode) {
                ForEach(BackendMode.allCases) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
            .pickerStyle(.segmented)

            Text(baseURL)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .card()
    }

    // MARK: - Location

    private var locationCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("1. Find Location")
                .font(.headline)

            TextField("Enter city, ZIP, or address", text: $locationText)
                .textFieldStyle(.roundedBorder)
                .textInputAutocapitalization(.words)

            Button {
                Task {
                    await findLocation()
                }
            } label: {
                fullButton(
                    title: "Find Location",
                    icon: "location.magnifyingglass",
                    loading: isFindingLocation
                )
            }
            .disabled(locationText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isFindingLocation)
        }
        .card()
    }

    private func selectedLocationCard(_ location: GeocodeResult) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Selected Location")
                .font(.headline)

            Text(location.display_name)
                .font(.subheadline)
                .fontWeight(.semibold)

            Text("Lat \(location.lat, specifier: "%.4f"), Lon \(location.lon, specifier: "%.4f")")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .card()
    }

    // MARK: - Scenario

    private var scenarioCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("2. Scenario")
                .font(.headline)

            Picker("Manual Scenario", selection: $scenario) {
                ForEach(Scenario.allCases) { item in
                    Text(item.label).tag(item)
                }
            }
            .pickerStyle(.menu)

            if alerts?.alerts?.isEmpty == false {
                Divider()

                HStack {
                    Image(systemName: "wand.and.stars")
                        .foregroundStyle(.blue)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Alert-based scenario")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        Text(inferredScenario.label)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }

                    Spacer()
                }

                Text("When alerts are available, Evac-AI uses the alert text to focus the action plan on the real hazard.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .card()
    }

    // MARK: - Situation Fetch

    private var situationButtonCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("3. Situation Intelligence")
                .font(.headline)

            Text("Fetches live weather, official alerts, nearby resources, and ML risk from the backend.")
                .font(.caption)
                .foregroundStyle(.secondary)

            Button {
                Task {
                    await fetchSituationData()
                }
            } label: {
                fullButton(
                    title: "Fetch Situation Data",
                    icon: "arrow.triangle.2.circlepath",
                    loading: isFetchingData
                )
            }
            .disabled(isFetchingData)
        }
        .card()
    }

    private var situationCards: some View {
        VStack(spacing: 14) {
            if let weather {
                weatherCard(weather)
            }

            if let alerts {
                alertsCard(alerts)
            }

            if let resources {
                resourcesCard(resources)
            }

            if let risk {
                riskCard(risk)
            }
        }
    }

    // MARK: - Weather Card

    private func weatherCard(_ weather: WeatherResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Live Weather", systemImage: "cloud.sun")
                .font(.headline)

            Text("Temperature: \(format(weather.current?.temperature_2m))")
            Text("Feels like: \(format(weather.current?.apparent_temperature))")
            Text("Precipitation: \(format(weather.current?.precipitation)) mm")
            Text("Wind: \(format(weather.current?.wind_speed_10m))")
            Text("Timezone: \(weather.timezone ?? "Unknown")")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .card()
    }

    // MARK: - Alerts Card

    private func alertsCard(_ alerts: AlertsResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Official Alerts", systemImage: "exclamationmark.triangle")
                .font(.headline)

            let items = alerts.alerts ?? []

            if items.isEmpty {
                Text("No active official alerts found.")
                    .foregroundStyle(.secondary)
            } else {
                Text("\(items.count) active alert(s) found. These details will be sent into the AI action plan.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                ForEach(items.prefix(5)) { alert in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(alert.headline ?? alert.event ?? "Emergency Alert")
                            .fontWeight(.semibold)

                        HStack {
                            Text("Severity: \(alert.severity ?? "Unknown")")
                            Text("Urgency: \(alert.urgency ?? "Unknown")")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)

                        if let description = alert.description, !description.isEmpty {
                            Text(description)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(4)
                        }

                        if let instruction = alert.instruction, !instruction.isEmpty {
                            Text("Instruction: \(instruction)")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundStyle(.orange)
                                .lineLimit(4)
                        }
                    }

                    Divider()
                }
            }
        }
        .card()
    }

    // MARK: - Resources Card

    private func resourcesCard(_ resources: ResourcesResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Nearby Resources", systemImage: "cross.case")
                .font(.headline)

            let items = resources.items ?? []

            Text("\(items.count) resources shown")
                .foregroundStyle(.secondary)

            ForEach(items.prefix(5)) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.name)
                        .fontWeight(.semibold)

                    Text("\(item.category) • \(format(item.distance_mi ?? item.distance_km)) \(item.distance_mi == nil ? "km" : "mi")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Divider()
            }
        }
        .card()
    }

    // MARK: - Risk Card

    private func riskCard(_ risk: RiskResponse) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("ML Risk Prediction", systemImage: "brain.head.profile")
                    .font(.headline)

                Spacer()

                Text(risk.risk_level ?? "Unknown")
                    .font(.caption)
                    .fontWeight(.bold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(riskColor(risk.risk_level).opacity(0.18))
                    .foregroundStyle(riskColor(risk.risk_level))
                    .clipShape(Capsule())
            }

            Text("Score: \(risk.risk_score ?? 0)/100")
                .font(.title3)
                .fontWeight(.bold)

            Text("Confidence: \(percent(risk.confidence))")

            if let model = risk.model {
                Text("Model: \(model)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let reasons = risk.reasons, !reasons.isEmpty {
                Text("Reasons")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                ForEach(reasons, id: \.self) { reason in
                    Text("• \(reason)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .card()
    }

    // MARK: - Plan Button

    private var planButtonCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("4. Generate AI Action Plan")
                .font(.headline)

            Text("Sends full official alert details, weather, nearby resources, and ML risk summary to the backend.")
                .font(.caption)
                .foregroundStyle(.secondary)

            if alerts?.alerts?.isEmpty == false {
                HStack {
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundStyle(.green)

                    Text("Action plan will follow the detected alert scenario: \(inferredScenario.label)")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)

                    Spacer()
                }
            }

            Button {
                Task {
                    await generatePlan()
                }
            } label: {
                fullButton(
                    title: "Generate Alert-Aligned Action Plan",
                    icon: "sparkles",
                    loading: isGeneratingPlan
                )
            }
            .disabled(isGeneratingPlan)
        }
        .card()
    }

    // MARK: - Plan Card

    private func planCard(_ response: PlanResponse) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("AI Action Plan", systemImage: "doc.text")
                    .font(.headline)

                Spacer()

                Text(response.demo_fallback == true ? "Demo" : "Live")
                    .font(.caption)
                    .fontWeight(.bold)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background((response.demo_fallback == true ? Color.orange : Color.green).opacity(0.18))
                    .foregroundStyle(response.demo_fallback == true ? .orange : .green)
                    .clipShape(Capsule())
            }

            Text("Scenario used: \(inferredScenario.label)")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundStyle(.blue)

            if let source = response.source {
                Text("Source: \(source)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let modelID = response.model_id {
                Text("Model: \(modelID)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if let error = response.error {
                Text("Backend message: \(error)")
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .textSelection(.enabled)
            }

            if let hint = response.hint {
                Text(hint)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if let plan = response.plan {
                section("Risk Summary", text: plan.risk_summary)
                section("What To Do Now", list: plan.what_to_do_now)
                section("Emergency Kit", list: plan.emergency_kit)
                section("Evacuation Guidance", list: plan.evacuation_guidance)
                section("Nearby Support", list: plan.nearby_support)
                section("Family Message", text: plan.family_message)
                section("Official Alert Reminder", text: plan.official_alert_reminder)
                section("Sources", list: plan.sources)
            } else if let raw = response.raw_text {
                Text(raw)
                    .textSelection(.enabled)
            } else {
                Text("No plan content returned.")
                    .foregroundStyle(.secondary)
            }
        }
        .card()
    }

    // MARK: - Error Card

    private func errorCard(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Error", systemImage: "exclamationmark.circle")
                .font(.headline)
                .foregroundStyle(.red)

            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .card()
    }

    // MARK: - Actions

    private func findLocation() async {
        isFindingLocation = true
        errorMessage = nil
        selectedLocation = nil
        weather = nil
        alerts = nil
        resources = nil
        risk = nil
        plan = nil

        do {
            let results = try await APIService.shared.geocode(
                baseURL: baseURL,
                query: locationText
            )

            guard let first = results.first else {
                throw NSError(
                    domain: "EvacAI",
                    code: 404,
                    userInfo: [NSLocalizedDescriptionKey: "No location found."]
                )
            }

            selectedLocation = first
        } catch {
            errorMessage = error.localizedDescription
        }

        isFindingLocation = false
    }

    private func fetchSituationData() async {
        guard let selectedLocation else { return }

        isFetchingData = true
        errorMessage = nil
        weather = nil
        alerts = nil
        resources = nil
        risk = nil
        plan = nil

        do {
            async let weatherTask = APIService.shared.weather(
                baseURL: baseURL,
                lat: selectedLocation.lat,
                lon: selectedLocation.lon
            )

            async let alertsTask = APIService.shared.alerts(
                baseURL: baseURL,
                lat: selectedLocation.lat,
                lon: selectedLocation.lon
            )

            async let resourcesTask = APIService.shared.resources(
                baseURL: baseURL,
                lat: selectedLocation.lat,
                lon: selectedLocation.lon
            )

            let fetchedWeather = try await weatherTask
            let fetchedAlerts = try await alertsTask
            let fetchedResources = try await resourcesTask

            weather = fetchedWeather
            alerts = fetchedAlerts
            resources = fetchedResources

            risk = try await APIService.shared.risk(
                baseURL: baseURL,
                location: selectedLocation,
                weather: fetchedWeather,
                alerts: fetchedAlerts,
                resources: fetchedResources
            )
        } catch {
            errorMessage = error.localizedDescription
        }

        isFetchingData = false
    }

    private func generatePlan() async {
        guard let selectedLocation else { return }

        isGeneratingPlan = true
        errorMessage = nil
        plan = nil

        do {
            plan = try await APIService.shared.plan(
                baseURL: baseURL,
                location: selectedLocation,
                scenario: scenarioFromAlerts(),
                alertsSummary: alertsSummary(),
                weatherSummary: weatherSummary(),
                resourcesSummary: resourcesSummary(),
                riskSummary: riskSummary()
            )
        } catch {
            errorMessage = error.localizedDescription
        }

        isGeneratingPlan = false
    }

    // MARK: - Alert-Aware Scenario Inference

    private func scenarioFromAlerts() -> Scenario {
        let text = (alerts?.alerts ?? [])
            .map { alert in
                [
                    alert.event,
                    alert.headline,
                    alert.description,
                    alert.instruction
                ]
                .compactMap { $0 }
                .joined(separator: " ")
            }
            .joined(separator: " ")
            .lowercased()

        if text.isEmpty {
            return scenario
        }

        if text.contains("heat") ||
            text.contains("excessive heat") ||
            text.contains("heat advisory") ||
            text.contains("extreme temperature") {
            return .heatwave
        }

        if text.contains("flood") ||
            text.contains("flash flood") ||
            text.contains("coastal flood") ||
            text.contains("river flood") {
            return .flood
        }

        if text.contains("wildfire") ||
            text.contains("smoke") ||
            text.contains("air quality") ||
            text.contains("poor air quality") {
            return .wildfireSmoke
        }

        if text.contains("winter") ||
            text.contains("snow") ||
            text.contains("ice") ||
            text.contains("blizzard") ||
            text.contains("freezing") {
            return .winterStorm
        }

        if text.contains("hurricane") ||
            text.contains("tropical storm") ||
            text.contains("storm surge") {
            return .hurricane
        }

        if text.contains("power") ||
            text.contains("outage") ||
            text.contains("blackout") {
            return .powerOutage
        }

        return scenario
    }

    // MARK: - Summary Builders Sent to Backend

    private func weatherSummary() -> String? {
        guard let current = weather?.current else {
            return "No weather data available."
        }

        return """
        Weather snapshot:
        Temperature: \(format(current.temperature_2m))
        Feels-like temperature: \(format(current.apparent_temperature))
        Precipitation: \(format(current.precipitation)) mm
        Wind speed: \(format(current.wind_speed_10m))
        Weather code: \(current.weather_code.map(String.init) ?? "Unknown")
        Time: \(current.time ?? "Unknown")
        """
    }

    private func alertsSummary() -> String? {
        guard let items = alerts?.alerts else {
            return "No alert data available."
        }

        if items.isEmpty {
            return "No active official emergency alerts were found for this location."
        }

        return items.prefix(5).enumerated().map { index, alert in
            let title = alert.headline ?? alert.event ?? "Emergency alert"
            let severity = alert.severity ?? "Unknown"
            let urgency = alert.urgency ?? "Unknown"
            let certainty = alert.certainty ?? "Unknown"
            let description = alert.description ?? "No description provided."
            let instruction = alert.instruction ?? "No official instruction provided."
            let effective = alert.effective ?? "Unknown effective time"
            let expires = alert.expires ?? "Unknown expiration"
            let sender = alert.senderName ?? "Unknown sender"

            return """
            Official Alert \(index + 1):
            Title: \(title)
            Severity: \(severity)
            Urgency: \(urgency)
            Certainty: \(certainty)
            Sender: \(sender)
            Effective: \(effective)
            Expires: \(expires)
            Description: \(description)
            Official instruction: \(instruction)
            """
        }.joined(separator: "\n\n")
    }

    private func resourcesSummary() -> String? {
        guard let items = resources?.items else {
            return "No nearby resource data available."
        }

        if items.isEmpty {
            return "No nearby shelters, clinics, hospitals, food banks, or community centers were found."
        }

        let grouped = Dictionary(grouping: items, by: { $0.category })
            .mapValues { $0.count }

        let countSummary = grouped
            .map { "\($0.key): \($0.value)" }
            .sorted()
            .joined(separator: ", ")

        let topResources = items.prefix(5).map { item in
            let distance = item.distance_mi ?? item.distance_km
            let distanceLabel = item.distance_mi == nil ? "km" : "mi"

            return "- \(item.name) (\(item.category)), distance: \(format(distance)) \(distanceLabel)"
        }.joined(separator: "\n")

        return """
        Nearby resource summary:
        Total resources found: \(items.count)
        Category counts: \(countSummary)
        Closest resources:
        \(topResources)
        """
    }

    private func riskSummary() -> String? {
        guard let risk else {
            return "No ML risk prediction available."
        }

        let reasons = risk.reasons?.joined(separator: ", ") ?? "No reasons returned."

        return """
        ML risk assessment:
        Risk level: \(risk.risk_level ?? "unknown")
        Risk score: \(risk.risk_score ?? 0)/100
        Confidence: \(percent(risk.confidence))
        Model: \(risk.model ?? "Unknown")
        Reasons: \(reasons)
        """
    }

    // MARK: - UI Helpers

    private func fullButton(title: String, icon: String, loading: Bool) -> some View {
        HStack {
            if loading {
                ProgressView()
                    .tint(.white)
            } else {
                Image(systemName: icon)
            }

            Text(loading ? "Loading..." : title)
                .fontWeight(.semibold)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color.blue)
        .foregroundStyle(.white)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func section(_ title: String, text: String?) -> some View {
        Group {
            if let text, !text.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.headline)

                    Text(text)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func section(_ title: String, list: [String]?) -> some View {
        Group {
            if let list, !list.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.headline)

                    ForEach(list, id: \.self) { item in
                        Text("• \(item)")
                            .textSelection(.enabled)
                    }
                }
            }
        }
    }

    private func riskColor(_ level: String?) -> Color {
        switch level?.lowercased() {
        case "high":
            return .red
        case "medium":
            return .orange
        case "low":
            return .green
        default:
            return .gray
        }
    }

    private func format(_ value: Double?) -> String {
        guard let value else { return "?" }
        return String(format: "%.1f", value)
    }

    private func percent(_ value: Double?) -> String {
        guard let value else { return "?" }
        return "\(Int(value * 100))%"
    }
}

// MARK: - Card Style

private extension View {
    func card() -> some View {
        self
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color(.secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 18))
    }
}
