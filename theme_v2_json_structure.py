theme_v2 = {
    "pages": {
        "home": {  # API key: pages_home  GET values key=pages_home
            "slug": "unique-custom-slug",

            # //{atom name}_{section}_{index}
            "sections": [
                {
                    "key": "hero_v1_home_1",
                    #-- the key is mandatory
                    "type": "hero_v1",
                    "visible": True,
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "image": "url"
                },
                {
                    "key": "two_columns_v1_home_1",
                    #-- the key is mandatory
                    "type": "two_columns_v1",
                    "visible": True,
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "columns_section": [
                         #--first column
                         {
                             "key": "first_column",#-- the key is mandatory
                             "title": {
                                 "ar": "عربي",
                                 "en": "Our Vision"
                             },
                             "description": {
                                 "ar": "عربي",
                                 "en": "Our Vision description"
                             },
                             "content_alignment": "start",
                             #-- 'start'| 'center' | 'end',
                             "icon": "fa-check",
                             #--#-- other icon names might be set here
                         },
                         #--second column
                         {
                             "key": "second_column",#-- the key is mandatory
                             "title": {
                                 "ar": "عربي",
                                 "en": "Our mission"
                             },
                             "description": {
                                 "ar": "عربي",
                                 "en": "Our mission description"
                             },
                             "content_alignment": "start",
                             #-- 'start'| 'center' | 'end',
                             "icon": "fa-check",
                             #--#-- other icon names might be set here
                         }
                    ],
                },
                {
                    "key": "side_image_v1_home_1",
                    "type": "side_image_v1",
                    "visible": True,
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "image": "url",
                    "reversed": False,  #--  False: flex: row | True: flex: row-reverse
                },
                {
                    "key": "featured_courses_v1_home_1",
                    "type": "featured_courses_v1",
                    "visible": True,
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "grid_type": "max-9" #-- accept max-3 | max-6 | max-9 | all | categorised
                },
                {
                    "key": "static_metrics_section_v1_home_1",
                    "type": "static_metrics_section_v1",
                    "visible": True,
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "alignment": "center",
                    #-- start | end | center
                    "list_of_static_metrics": [
                        {
                            "key": "metric_1",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        },
                        {
                            "key": "metric_2",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        },
                        {
                            "key": "metric_3",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        }
                    ]
                },
                {
                    "key": "live_metrics_section_v1_home_1",
                    "type": "live_metrics_section_v1",
                    "visible": True,
                    "options": [
                        {
                            "key": "courses",
                            "is_checked": True,
                            #-- the value is boolean
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        },
                        {
                            "key": "learners",
                            "is_checked": True,
                            #-- the value is boolean
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        },
                        {
                            "key": "instructors",
                            "is_checked": True,
                            #-- the value is boolean
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        }
                    ]
                },
            ]
        },
        "courses": {
            #--#--  API key: pages_courses
        },
        "about_us": {
            #--#--  API key: pages_about_us
        },
        "terms": {
            #--#--  API key: pages_terms
        },
        "contact_us": {
            #--#--  API key: pages_contact_us
        },
        "pages_custom_page_1": {
            #--#--  API key: pages_custom_page_1
            "sections": [
                # .... the rest of the properties
            ],
            #--#-- other details similar to home
        },
        "pages_custom_page_2": {
            #--#--  API key: pages_custom_page_2
            "slug": "unique-custom-slug",

            "sections": [
                # .... the rest of the properties
            ],
            #--#-- other details similar to home
        },
        "pages_custom_page_3": {  #--  API key: pages_custom_page_3
            "slug": "unique-custom-slug",

            "sections": [
                # .... the rest of the properties
            ],
            #--#-- other details similar to home
        },

        "pages_custom_page_4": {},  #--  API key: pages_custom_page_4

        "pages_custom_page_5": {},  #--  API key: pages_custom_page_5

        "pages_custom_page_6": {},  # --  API key: pages_custom_page_6

        "pages_custom_page_7": {},  #--  API key: pages_custom_page_7

        "pages_custom_page_8": {},  #--  API key: pages_custom_page_8
    },

    "custom_pages": [  #--#--  API key: custom_pages, maximum 8 pages
        "pages_custom_page_1",
        "pages_custom_page_2",
        "pages_custom_page_5"
    ],

    "visual_identity": {
        "colors": {
            "primary_color: "#00ff00",  #--  API key: colors_primary_color
            "secondary_color: "#00ff00",  #--  API key: colors_secondary_color
        },
        "fonts": {
            "heading": {  #--  API key: fonts_heading
                "ar":"",
                "en":""
            },
            "text": {  #--  API key: fonts_text
                "ar":"",
                "en":""
            }
        }
    },

    "platform_settings": {  #--  API key: platform_settings
        "language": {  #--  API key: platform_settings_language
            "languages": [
                "ar", "en", "fr"
            ],
            "default_language": "ar",
        },
        "site_name": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
        "subtitle": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
        "favicon": "url",
        "thumbnail": "url",
        "social_media_image": "url",
        "meta_description": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
    },

    "footer": {
        "sections": [  #--  API key: footer_sections
             {
                 "key": "option_1",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "courses",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
             {
                 "key": "option_2",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "about_us",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
             {
                 "key": "option_3",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "pages_custom_page_1",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
        ],
        "social_media_links": [  #--  API key: footer_social_media_links
            {
                "provider": "facebook",
                "value": "url"
            },
            {
                "provider": "x",
                "value": "url"
            }
        ]
    },

    "header": {
        "sections": [  #--  API key: header_sections
            {
                "key": "option_1",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "courses",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
            {
                "key": "option_2",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "about_us",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
            {
                "key": "option_3",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "pages_custom_page_1",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
        ],
        "combined_login": True,  #--  API key: header_combined_login
    },
}

root_settings = {
    "logo_image_url": "url",  #--  API key: logo_url
    "PLATFORM_NAME": "",  #--  API key: platform_name
}
