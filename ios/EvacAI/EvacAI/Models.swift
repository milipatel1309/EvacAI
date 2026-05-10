import Foundation

enum BackendMode: String, CaseIterable, Identifiable {
    case render = "Render"
    case local = "Local"

    var id: String { rawValue }

    var baseURL: String {
        switch self {
        case .render:
            return "https://evac-ai.onrender.com"
        case .local:
            return "http://127.0.0.1:8000"
        }
    }
}

enum Scenario: String, CaseIterable, Identifiable {
    case general = "general"
    case heatwave = "heatwave"
    case flood = "flood"
    case wildfireSmoke = "wildfire_smoke"
    case powerOutage = "power_outage"
    case winterStorm = "winter_storm"
    case hurricane = "hurricane"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .general: return "General"
        case .heatwave: return "Heatwave"
        case .flood: return "Flood"
        case .wildfireSmoke: return "Wildfire Smoke"
        case .powerOutage: return "Power Outage"
        case .winterStorm: return "Winter Storm"
        case .hurricane: return "Hurricane"
        }
    }
}

struct GeocodeResponse: Codable {
    let source: String?
    let results: [GeocodeResult]
    let note: String?
}

struct GeocodeResult: Codable, Identifiable {
    var id: String { "\(lat)-\(lon)-\(display_name)" }

    let display_name: String
    let lat: Double
    let lon: Double

    enum CodingKeys: String, CodingKey {
        case display_name
        case lat
        case lon
    }

    init(display_name: String, lat: Double, lon: Double) {
        self.display_name = display_name
        self.lat = lat
        self.lon = lon
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        display_name = try container.decode(String.self, forKey: .display_name)
        lat = try container.decodeFlexibleDouble(forKey: .lat)
        lon = try container.decodeFlexibleDouble(forKey: .lon)
    }
}

struct WeatherResponse: Codable {
    let source: String?
    let current: WeatherCurrent?
    let timezone: String?
    let timezone_abbreviation: String?
    let wind_speed_unit: String?
}

struct WeatherCurrent: Codable {
    let time: String?
    let interval: Int?
    let temperature_2m: Double?
    let apparent_temperature: Double?
    let precipitation: Double?
    let rain: Double?
    let showers: Double?
    let weather_code: Int?
    let wind_speed_10m: Double?
}

struct AlertsResponse: Codable {
    let source: String?
    let alerts: [AlertItem]?
    let count: Int?
}

struct AlertItem: Codable, Identifiable {
    var id: String { "\(event ?? headline ?? UUID().uuidString)-\(severity ?? "")" }

    let event: String?
    let severity: String?
    let urgency: String?
    let certainty: String?
    let headline: String?
    let description: String?
    let instruction: String?
    let effective: String?
    let expires: String?
    let senderName: String?
    let web: String?
}

struct ResourcesResponse: Codable {
    let source: String?
    let items: [ResourceItem]?
    let count: Int?
    let radius_km: Double?
    let radius_mi: Double?
    let types: [String]?
    let note: String?
}

struct ResourceItem: Codable, Identifiable {
    var id: String { "\(name)-\(category)-\(lat)-\(lon)" }

    let name: String
    let category: String
    let lat: Double
    let lon: Double
    let distance_km: Double?
    let distance_mi: Double?
    let address: ResourceAddress?
    let phone: String?
    let website: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case name
        case category
        case lat
        case lon
        case distance_km
        case distance_mi
        case address
        case phone
        case website
        case source
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? container.decode(String.self, forKey: .name)) ?? "Unnamed resource"
        category = (try? container.decode(String.self, forKey: .category)) ?? "resource"
        lat = (try? container.decodeFlexibleDouble(forKey: .lat)) ?? 0
        lon = (try? container.decodeFlexibleDouble(forKey: .lon)) ?? 0
        distance_km = try? container.decodeFlexibleDouble(forKey: .distance_km)
        distance_mi = try? container.decodeFlexibleDouble(forKey: .distance_mi)
        address = try? container.decode(ResourceAddress.self, forKey: .address)
        phone = try? container.decode(String.self, forKey: .phone)
        website = try? container.decode(String.self, forKey: .website)
        source = try? container.decode(String.self, forKey: .source)
    }
}

struct ResourceAddress: Codable {
    let street: String?
    let housenumber: String?
    let city: String?
    let state: String?
    let postcode: String?
    let country: String?
}

struct RiskPostRequest: Codable {
    let lat: Double
    let lon: Double
    let alerts: RiskAlertsInput
    let weather: RiskWeatherInput
    let resources: RiskResourcesInput
}

struct RiskAlertsInput: Codable {
    let count: Int?
    let max_severity: String?
}

struct RiskWeatherInput: Codable {
    let wind_speed: Double?
    let precip_mm: Double?
    let temp_f: Double?
    let temp_c: Double?
}

struct RiskResourcesInput: Codable {
    let count: Int?
    let radius_km: Double?
}

struct RiskResponse: Codable {
    let risk_level: String?
    let risk_score: Int?
    let confidence: Double?
    let reasons: [String]?
    let model: String?
    let model_kind: String?
}

struct PlanRequest: Codable {
    let lat: Double
    let lon: Double
    let location_display: String?
    let scenario: String
    let alerts_summary: String?
    let weather_summary: String?
    let resources_summary: String?
    let risk_summary: String?
    let archive_to_cos: Bool
}

struct PlanResponse: Codable {
    let source: String?
    let provider: String?
    let model_id: String?
    let demo_fallback: Bool?
    let plan: ActionPlan?
    let raw_text: String?
    let error: String?
    let hint: String?

    enum CodingKeys: String, CodingKey {
        case source
        case provider
        case model_id
        case demo_fallback
        case plan
        case raw_text
        case error
        case hint
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        source = try? container.decode(String.self, forKey: .source)
        provider = try? container.decode(String.self, forKey: .provider)
        model_id = try? container.decode(String.self, forKey: .model_id)
        demo_fallback = try? container.decode(Bool.self, forKey: .demo_fallback)
        plan = try? container.decode(ActionPlan.self, forKey: .plan)
        raw_text = try? container.decode(String.self, forKey: .raw_text)
        error = try? container.decode(String.self, forKey: .error)
        hint = try? container.decode(String.self, forKey: .hint)
    }
}

struct ActionPlan: Codable {
    let risk_summary: String?
    let what_to_do_now: [String]?
    let emergency_kit: [String]?
    let evacuation_guidance: [String]?
    let nearby_support: [String]?
    let family_message: String?
    let official_alert_reminder: String?
    let sources: [String]?
}

extension KeyedDecodingContainer {
    func decodeFlexibleDouble(forKey key: Key) throws -> Double {
        if let doubleValue = try? decode(Double.self, forKey: key) {
            return doubleValue
        }

        if let intValue = try? decode(Int.self, forKey: key) {
            return Double(intValue)
        }

        if let stringValue = try? decode(String.self, forKey: key),
           let doubleValue = Double(stringValue) {
            return doubleValue
        }

        throw DecodingError.typeMismatch(
            Double.self,
            DecodingError.Context(
                codingPath: codingPath + [key],
                debugDescription: "Expected Double, Int, or numeric String"
            )
        )
    }
}
