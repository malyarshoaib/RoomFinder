package com.campus.roomfinder.loader;

import ch.qos.logback.core.encoder.EchoEncoder;
import com.campus.roomfinder.entity.CourseSchedule;
import com.campus.roomfinder.repository.CourseScheduleRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class CourseDataLoader implements CommandLineRunner {

    private final CourseScheduleRepository repository;


    public CourseDataLoader(CourseScheduleRepository repository){
        this.repository = repository;
    }

    public void run (String... args) throws Exception{
        if (repository.count() > 0) {
            System.out.println("ℹ️ Database already contains records. Skipping CSV import.");
            return;
        }

        List<CourseSchedule> schedules = new ArrayList<>();

        ClassPathResource resource = new ClassPathResource("in_person_classes.csv");

        try(BufferedReader reader = new BufferedReader(new InputStreamReader(resource.getInputStream(), StandardCharsets.UTF_8))) {
            reader.readLine(); // Skip header
            String data;

            // Compile the pattern once outside the loop for better performance
            String regex = "^(.*?)\\s+Room\\s+([A-Za-z0-9]+)";
            Pattern pattern = Pattern.compile(regex);

            while ((data = reader.readLine()) != null) {
                String[] columns = data.split(",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)");

                // 2. The schedule information is at index 6 (the 7th column)
                if (columns.length <= 6) continue; // Safety check
                String scheduleInfo = columns[6];

                // 3. Split the schedule string by the pipe character '|'
                String[] scheduleParts = scheduleInfo.split("\\|");

                // 4. Extract and trim the parts
                if (scheduleParts.length >= 3) {
                    String days = scheduleParts[0].trim();
                    String time = scheduleParts[1].trim();
                    String room = scheduleParts[2].trim();

                    String[] splitTime = time.split("-");
                    String startTimeStr = splitTime[0].trim();
                    String endTimeStr = splitTime[1].trim();
                    DateTimeFormatter timeFormatter = DateTimeFormatter.ofPattern("h:mm a");
                    LocalTime startTime = LocalTime.parse(startTimeStr, timeFormatter);
                    LocalTime endTime = LocalTime.parse(endTimeStr, timeFormatter);

                    Matcher matcher = pattern.matcher(room);

                    if (matcher.find()) {
                        String building = matcher.group(1);
                        String roomNumber = matcher.group(2);

                        // Loop through each character in the 'days' string (e.g., 'M' then 'W')
                        for (char day : days.toCharArray()) {
                            // Skip any accidental spaces just in case the data has "M W"
                            if (day == ' ') continue;
                            schedules.add(new CourseSchedule(building, roomNumber, day, startTime, endTime));
                        }
                    }
                } else {
                    System.out.println("Schedule format was unexpected.");
                }
            }
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        repository.saveAll(schedules);
        System.out.println("✅ Imported " + schedules.size() + " schedule records into PostgreSQL!");
        }
    }




