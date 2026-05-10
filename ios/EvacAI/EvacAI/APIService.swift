import Foundation

final class APIService {
    static let shared = APIService()

    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    private init() {}

    func geocode(baseURL: String, query: String) async throws -> [GeocodeResult] {
        var components = try components(baseURL: baseURL, path: "/api/geocode")
        components.queryItems = [
            URLQueryItem(name: "q", value: query)
        ]

        let data = try await getData(components)
        let response = try decoder.decode(GeocodeResponse.self, from: data)
        return response.results
    }

    func weather(baseURL: String, lat: Double, lon: Double) async throws -> WeatherResponse {
        var components = try components(baseURL: baseURL, path: "/api/weather")
        components.queryItems = [
            URLQueryItem(name: "lat", value: String(lat)),
            URLQueryItem(name: "lon", value: String(lon))
        ]

        let data = try await getData(components)
        return try decoder.decode(WeatherResponse.self, from: data)
    }

    func alerts(baseURL: String, lat: Double, lon: Double, country: String = "auto") async throws -> AlertsResponse {
        var components = try components(baseURL: baseURL, path: "/api/alerts")
        components.queryItems = [
            URLQueryItem(name: "country", value: country),
            URLQueryItem(name: "scope", value: "point"),
            URLQueryItem(name: "lat", value: String(lat)),
            URLQueryItem(name: "lon", value: String(lon))
        ]

        let data = try await getData(components)
        return try decoder.decode(AlertsResponse.self, from: data)
    }

    func resources(baseURL: String, lat: Double, lon: Double) async throws -> ResourcesResponse {
        var components = try components(baseURL: baseURL, path: "/api/resources")
        components.queryItems = [
            URLQueryItem(name: "lat", value: String(lat)),
            URLQueryItem(name: "lon", value: String(lon)),
            URLQueryItem(name: "radius_mi", value: "10"),
            URLQueryItem(name: "types", value: "shelter,clinic,hospital,food_bank,community_centre")
        ]

        let data = try await getData(components)
        return try decoder.decode(ResourcesResponse.self, from: data)
    }

    func risk(
        baseURL: String,
        location: GeocodeResult,
        weather: WeatherResponse?,
        alerts: AlertsResponse?,
        resources: ResourcesResponse?
    ) async throws -> RiskResponse {
        let request = RiskPostRequest(
            lat: location.lat,
            lon: location.lon,
            alerts: RiskAlertsInput(
                count: alerts?.alerts?.count ?? alerts?.count ?? 0,
                max_severity: maxSeverity(alerts?.alerts ?? [])
            ),
            weather: RiskWeatherInput(
                wind_speed: weather?.current?.wind_speed_10m,
                precip_mm: weather?.current?.precipitation,
                temp_f: weather?.current?.temperature_2m,
                temp_c: nil
            ),
            resources: RiskResourcesInput(
                count: resources?.items?.count ?? resources?.count ?? 0,
                radius_km: resources?.radius_km
            )
        )

        let data = try await postJSON(
            baseURL: baseURL,
            path: "/api/risk",
            body: request
        )

        return try decoder.decode(RiskResponse.self, from: data)
    }

    func plan(
        baseURL: String,
        location: GeocodeResult,
        scenario: Scenario,
        alertsSummary: String?,
        weatherSummary: String?,
        resourcesSummary: String?,
        riskSummary: String?
    ) async throws -> PlanResponse {
        let request = PlanRequest(
            lat: location.lat,
            lon: location.lon,
            location_display: location.display_name,
            scenario: scenario.rawValue,
            alerts_summary: alertsSummary,
            weather_summary: weatherSummary,
            resources_summary: resourcesSummary,
            risk_summary: riskSummary,
            archive_to_cos: false
        )

        let data = try await postJSON(
            baseURL: baseURL,
            path: "/api/plan",
            body: request
        )

        return try decoder.decode(PlanResponse.self, from: data)
    }

    private func components(baseURL: String, path: String) throws -> URLComponents {
        guard let url = URL(string: baseURL + path),
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw URLError(.badURL)
        }
        return components
    }

    private func getData(_ components: URLComponents) async throws -> Data {
        guard let url = components.url else {
            throw URLError(.badURL)
        }

        let (data, response) = try await URLSession.shared.data(from: url)

        guard isSuccess(response) else {
            throw makeError(data: data, response: response)
        }

        return data
    }

    private func postJSON<T: Encodable>(
        baseURL: String,
        path: String,
        body: T
    ) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard isSuccess(response) else {
            throw makeError(data: data, response: response)
        }

        return data
    }

    private func isSuccess(_ response: URLResponse) -> Bool {
        guard let http = response as? HTTPURLResponse else {
            return false
        }
        return 200...299 ~= http.statusCode
    }

    private func makeError(data: Data, response: URLResponse) -> NSError {
        let code = (response as? HTTPURLResponse)?.statusCode ?? -1
        let body = String(data: data, encoding: .utf8) ?? "Unknown error"

        return NSError(
            domain: "EvacAIBackend",
            code: code,
            userInfo: [
                NSLocalizedDescriptionKey: "HTTP \(code): \(body)"
            ]
        )
    }

    private func maxSeverity(_ alerts: [AlertItem]) -> String? {
        let score: [String: Int] = [
            "minor": 1,
            "moderate": 2,
            "severe": 3,
            "extreme": 4
        ]

        var best: String?
        var bestScore = 0

        for alert in alerts {
            let severity = alert.severity?.lowercased() ?? ""
            let current = score[severity] ?? 0

            if current > bestScore {
                bestScore = current
                best = severity
            }
        }

        return best
    }
}
